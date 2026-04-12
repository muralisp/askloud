"""
DataLoader — reads JSON inventory files from disk, enriches records with
Account/Region/Provider metadata, builds field schemas, and resolves config
field names to jmespath paths.

State held here (all public so other modules can read it directly):
  configs        dict[rt, list[str]]          field names from .conf files
  data           dict[rt, list[dict]]          enriched records
  schemas        dict[rt, list[str]]           jmespath path strings for schema
  record_counts  dict[rt, int]
  field_maps     dict[rt, dict[str, str]]      config field → jmespath path
  populated_meta dict[rt, set[str]]            meta fields with real values
  file_sources   dict[rt, list[dict]]          loaded file metadata
"""

import os
import json
import re
from pathlib import Path

from .settings import (
    DATA_DIR, CONFIG_DIR,
    FIELD_ALIASES, DEDUP_FIELDS, NOISE_TAG_PREFIXES,
)


class DataLoader:

    def __init__(self):
        self.configs: dict        = {}
        self.data: dict           = {}
        self.schemas: dict        = {}
        self.record_counts: dict  = {}
        self.field_maps: dict     = {}
        self.populated_meta: dict = {}
        self.file_sources: dict   = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Public load methods
    # ─────────────────────────────────────────────────────────────────────────

    def load_configs(self):
        """Read all *.conf files under CONFIG_DIR."""
        self.configs = {}
        for root, _, files in os.walk(CONFIG_DIR):
            for fname in files:
                if not fname.endswith(".conf"):
                    continue
                resource = fname[:-5]
                with open(os.path.join(root, fname)) as fh:
                    self.configs[resource] = [
                        line.strip()
                        for line in fh
                        if line.strip() and not line.startswith("#")
                    ]

    def load_data(self):
        """Walk DATA_DIR, flatten records, inject Account/Region/Provider."""
        buffers: dict = {}
        for root, _, files in os.walk(DATA_DIR):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                resource_type = fname[:-5]
                rel_parts = os.path.relpath(root, DATA_DIR).split(os.sep)
                provider  = rel_parts[0] if rel_parts else "unknown"
                account, region = self._infer_metadata(rel_parts, provider)
                try:
                    with open(os.path.join(root, fname)) as fh:
                        raw = json.load(fh)
                except (json.JSONDecodeError, IOError):
                    continue

                records  = self._extract_records(raw)
                enriched = [
                    {"Account": account, "Region": region, "Provider": provider, **r}
                    for r in records
                ]
                buffers.setdefault(resource_type, []).extend(enriched)
                self.file_sources.setdefault(resource_type, []).append({
                    "file_path": os.path.join(root, fname),
                    "account":   account,
                    "region":    region,
                    "provider":  provider,
                })

        for rt, records in buffers.items():
            records = self._dedup(rt, records)
            self.data[rt]           = records
            self.record_counts[rt]  = len(records)
            self.populated_meta[rt] = self._compute_populated_meta(records)
            print(f"\033[90m  {rt}: {len(records)} records\033[0m")

    def extract_schemas(self):
        """Build field schemas for all loaded resource types."""
        for rt in self.data:
            self.extract_schemas_for(rt)

    def extract_schemas_for(self, rt: str):
        """Re-build schema for a single resource type."""
        records = self.data.get(rt, [])
        if not records:
            return
        paths    = self._field_paths(records[0])
        all_keys = self.all_tag_keys(records)
        if all_keys:
            paths = [
                p if not p.startswith("Tags[") else
                f"Tags[{{Key,Value}}]  # keys: {', '.join(all_keys)}"
                for p in paths
            ]
            if not any(p.startswith("Tags[") for p in paths):
                paths.append(f"Tags[{{Key,Value}}]  # keys: {', '.join(all_keys)}")
        self.schemas[rt] = paths

    def build_field_maps(self):
        """Resolve config field names to jmespath paths for all resource types."""
        for rt in self.data:
            self.build_field_maps_for(rt)

    def build_field_maps_for(self, rt: str):
        """Re-resolve field map for a single resource type."""
        records = self.data.get(rt, [])
        if not records:
            self.field_maps[rt] = {}
            return

        # Gather top-level scalar field names (lowercase → original case)
        top_level: dict = {}
        for r in records[:20]:
            for k, v in r.items():
                if not isinstance(v, (dict, list)):
                    top_level[k.lower()] = k

        # Gather all tag keys (lowercase → original case)
        tag_keys: dict = {k.lower(): k for k in self.all_tag_keys(records)}

        sample         = records[0]
        uses_dict_tags = isinstance(sample.get("tags"), dict) and not isinstance(sample.get("Tags"), list)
        global_aliases = FIELD_ALIASES.get("*", {})
        rt_aliases     = FIELD_ALIASES.get(rt, {})

        fmap: dict = {}
        for fname in self.configs.get(rt, []):
            fl = fname.lower()

            # 0. Literal jmespath expression (contains '.' or '[')
            if "." in fname or "[" in fname:
                fmap[fname] = fname
            # 1. Global alias
            elif fl in global_aliases:
                fmap[fname] = global_aliases[fl]
            # 2. Resource-specific alias
            elif fl in rt_aliases:
                fmap[fname] = rt_aliases[fl]
            # 3. Top-level scalar field (case-insensitive)
            elif fl in top_level:
                fmap[fname] = top_level[fl]
            # 4. Tag key (case-insensitive)
            elif fl in tag_keys:
                orig = tag_keys[fl]
                fmap[fname] = (
                    f"tags.{orig}" if uses_dict_tags
                    else f"Tags[?Key=='{orig}'].Value | [0]"
                )
            # 5. Recursive leaf search through nested objects and arrays
            else:
                path = self.find_leaf_path(records, fl)
                if path:
                    fmap[fname] = path
            # Unresolved fields are silently skipped at query time

        self.field_maps[rt] = fmap

    def prompt_tag_keys(self, rt: str) -> list:
        """
        Tag keys to include in the system prompt schema for a resource type.
        Filters out noise/system tags while always keeping any tag key referenced
        in the resource's config file.
        """
        config_tag_keys: set = set()
        for path in self.field_maps.get(rt, {}).values():
            m = re.search(r"Tags\[\?Key=='([^']+)'\]", path)
            if m:
                config_tag_keys.add(m.group(1))

        return [
            k for k in self.all_tag_keys(self.data.get(rt, []))
            if k in config_tag_keys
            or not any(k.startswith(p) for p in NOISE_TAG_PREFIXES)
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Static helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def find_leaf_path(records: list, field_lower: str, max_depth: int = 5):
        """
        Recursively search sample records for a leaf field whose name matches
        field_lower (case-insensitive). Returns a jmespath path string or None.
        Array nodes are indexed as [0] so the returned path is valid jmespath.
        """
        def search(obj, prefix, depth):
            if depth > max_depth or not isinstance(obj, dict):
                return None
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                if k.lower() == field_lower and not isinstance(v, (dict, list)):
                    return path
                if isinstance(v, dict):
                    result = search(v, path, depth + 1)
                    if result:
                        return result
                elif isinstance(v, list) and v and isinstance(v[0], dict):
                    result = search(v[0], f"{path}[0]", depth + 1)
                    if result:
                        return result
            return None

        for r in records[:10]:
            result = search(r, "", 0)
            if result:
                return result
        return None

    @staticmethod
    def all_tag_keys(records: list) -> list:
        """Collect every unique tag key across all records (AWS array and Azure dict formats)."""
        keys, seen = [], set()
        for r in records:
            for t in (r.get("Tags") or []):
                k = t.get("Key") if isinstance(t, dict) else None
                if k and k not in seen:
                    seen.add(k)
                    keys.append(k)
            azure_tags = r.get("tags")
            if isinstance(azure_tags, dict):
                for k in azure_tags:
                    if k and k not in seen:
                        seen.add(k)
                        keys.append(k)
        return keys

    @staticmethod
    def _extract_records(raw) -> list:
        """Flatten cloud-provider JSON into a list of record dicts."""
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
        if isinstance(raw, dict):
            if "Reservations" in raw:               # AWS EC2
                records = []
                for res in raw["Reservations"]:
                    records.extend(r for r in res.get("Instances", []) if isinstance(r, dict))
                return records
            for val in raw.values():                # Generic single-key wrapper
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    return val
        return []

    @staticmethod
    def _infer_metadata(rel_parts: list, provider: str):
        account, region = "N/A", "N/A"
        if provider == "aws":
            # Layout: aws/<account>/<region>/
            if len(rel_parts) >= 3:
                account = rel_parts[1]
                region  = rel_parts[2]
        elif provider in ("gcp", "azure"):
            if len(rel_parts) >= 2:
                account = rel_parts[1]
            if provider == "gcp" and len(rel_parts) >= 3:
                region = rel_parts[2]
        return account, region

    @staticmethod
    def _field_paths(obj, prefix="", depth=0, max_depth=2) -> list:
        if not isinstance(obj, dict) or depth >= max_depth:
            return []
        paths = []
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if key == "Tags" and isinstance(val, list):
                tag_keys = [t.get("Key") for t in val if isinstance(t, dict) and t.get("Key")]
                paths.append(f"{path}[{{Key,Value}}]  # keys: {', '.join(tag_keys[:15])}")
            elif isinstance(val, dict):
                paths.append(f"{path}  # object")
                paths.extend(DataLoader._field_paths(val, path, depth + 1, max_depth))
            elif isinstance(val, list) and val and isinstance(val[0], dict):
                paths.append(f"{path}[]  # array of objects")
            else:
                paths.append(path)
        return paths

    @staticmethod
    def _dedup(rt: str, records: list) -> list:
        dedup_field = DEDUP_FIELDS.get(rt)
        if not dedup_field:
            return records
        seen, deduped = set(), []
        for r in records:
            key = r.get(dedup_field)
            if key is None or key not in seen:
                seen.add(key)
                deduped.append(r)
        removed = len(records) - len(deduped)
        if removed:
            print(f"\033[90m  {rt}: removed {removed} duplicate(s) by {dedup_field}\033[0m")
        return deduped

    @staticmethod
    def _compute_populated_meta(records: list) -> set:
        return {
            f for f in ("Account", "Region", "Provider")
            if any(r.get(f, "N/A") != "N/A" for r in records)
        }
