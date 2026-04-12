"""
Live data refresh — runs a cloud CLI command, merges the result into the
DataLoader's in-memory dataset, and persists it to disk.

execute_refresh(step, loader) → bool
  Returns True on success so the caller can rebuild the system prompt.
"""

import os
import json
import subprocess
from pathlib import Path

from .settings import PROVIDER_CLI, PROVIDER_OUTPUT_FLAG, DEDUP_FIELDS, CLI_TIMEOUT
from .loader import DataLoader


def execute_refresh(step: dict, loader: DataLoader) -> bool:
    """
    Fetch fresh data from a cloud provider CLI and merge it into the loader.

    step keys:
      provider   — "aws" | "azure" | "gcp"
      resource   — resource type name (e.g. "ec2")
      args       — CLI args without the binary or --output flag
      file_path  — destination JSON file path
      scope      — dict for targeted merge (e.g. {"Region": "us-east-1", "Account": "Prod"})

    Returns True if data was fetched and merged successfully, False otherwise.
    """
    provider  = step.get("provider", "aws").lower()
    resource  = step.get("resource", "")
    args      = step.get("args", [])
    file_path = step.get("file_path", "")
    scope     = step.get("scope", {})

    if provider not in PROVIDER_CLI:
        print(f"\033[31mUnknown provider '{provider}'.\033[0m")
        return False

    cli = PROVIDER_CLI[provider]
    args = _inject_aws_profile(provider, args, file_path, scope)
    cmd = [cli] + args + PROVIDER_OUTPUT_FLAG[provider]
    print(f"\033[90m  → {' '.join(cmd)}\033[0m")

    raw_data = _run_cli(cli, cmd)
    if raw_data is None:
        return False

    new_records = loader._extract_records(raw_data)
    if not new_records:
        print("\033[33mNo records returned from CLI.\033[0m")
        return False

    meta = _resolve_meta(provider, file_path, scope, loader, resource)
    enriched_new = [
        {"Account": meta["Account"], "Region": meta["Region"], "Provider": meta["Provider"], **r}
        for r in new_records
    ]

    merged = _merge(resource, enriched_new, scope, loader)

    # Persist to disk
    if file_path:
        dest = Path(file_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w") as fh:
            json.dump(raw_data, fh, indent=2, default=str)
        # Update file sources index
        sources     = loader.file_sources.setdefault(resource, [])
        known_paths = [s["file_path"] for s in sources]
        if file_path not in known_paths:
            sources.append({"file_path": file_path, **meta})

    # Update loader state
    added   = len(enriched_new)
    removed = len(loader.data.get(resource, [])) + len(enriched_new) - len(merged)

    loader.data[resource]           = merged
    loader.record_counts[resource]  = len(merged)
    loader.populated_meta[resource] = loader._compute_populated_meta(merged)
    loader.extract_schemas_for(resource)
    loader.build_field_maps_for(resource)

    print(
        f"\033[32m  Refreshed '{resource}': {added} new records fetched, "
        f"{len(merged)} total in dataset"
        + (f", {removed} duplicates removed" if removed > 0 else "")
        + (f"  → saved to {file_path}" if file_path else "")
        + "\033[0m"
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_cli(cli: str, cmd: list):
    """Run the CLI command and return parsed JSON, or None on error."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT)
    except FileNotFoundError:
        print(f"\033[31mCLI '{cli}' not found. Is it installed?\033[0m")
        return None
    except subprocess.TimeoutExpired:
        print(f"\033[31mCLI command timed out after {CLI_TIMEOUT}s.\033[0m")
        return None

    if result.returncode != 0:
        print(f"\033[31mCLI error: {result.stderr.strip()[:300]}\033[0m")
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"\033[31mCould not parse CLI output as JSON: {e}\033[0m")
        return None


def _resolve_meta(provider: str, file_path: str, scope: dict, loader: DataLoader, resource: str) -> dict:
    """Determine Account/Region/Provider for the refreshed records."""
    meta = {"Account": "N/A", "Region": "N/A", "Provider": provider}
    for src in loader.file_sources.get(resource, []):
        if file_path and os.path.normpath(src["file_path"]) == os.path.normpath(file_path):
            meta = {"Account": src["account"], "Region": src["region"], "Provider": src["provider"]}
            break
    # Fallback: use values from the scope dict
    if meta["Account"] == "N/A" and scope.get("Account"):
        meta["Account"] = scope["Account"]
    if meta["Region"] == "N/A" and scope.get("Region"):
        meta["Region"] = scope["Region"]
    return meta


def _inject_aws_profile(provider: str, args: list, file_path: str, scope: dict) -> list:
    """
    For AWS refreshes, automatically append --profile <account> if not already present.
    The account is derived from the file_path (data/aws/accounts/<account>/...) or scope.
    """
    if provider != "aws" or "--profile" in args:
        return args
    account = scope.get("Account", "")
    if not account and file_path:
        parts = Path(file_path).parts
        # Expected: data / aws / accounts / <account> / ...
        try:
            idx = list(parts).index("accounts")
            account = parts[idx + 1]
        except (ValueError, IndexError):
            pass
    if account and account != "N/A":
        return args + ["--profile", account]
    return args


def _merge(resource: str, enriched_new: list, scope: dict, loader: DataLoader) -> list:
    """
    Merge new records into the existing dataset using a scope-based strategy:
      - Targeted  (scope has only the dedup field): replace the single matching record.
      - Regional  (scope has Region/Account):       replace all records in that slice.
      - Full      (no scope):                       replace the entire dataset.
    Then re-deduplicate by the dedup field.
    """
    existing   = list(loader.data.get(resource, []))
    dedup_field = DEDUP_FIELDS.get(resource)

    if scope and len(scope) == 1 and dedup_field and dedup_field in scope:
        target_id = scope[dedup_field]
        existing  = [r for r in existing if r.get(dedup_field) != target_id]
    elif scope.get("Region") or scope.get("Account"):
        r_filter = scope.get("Region")
        a_filter = scope.get("Account")
        existing = [
            r for r in existing
            if not (
                (not r_filter or r.get("Region") == r_filter) and
                (not a_filter or r.get("Account") == a_filter)
            )
        ]
    else:
        existing = []

    merged = existing + enriched_new

    if dedup_field:
        seen, deduped = set(), []
        for r in merged:
            key = r.get(dedup_field)
            if key is None or key not in seen:
                seen.add(key)
                deduped.append(r)
        merged = deduped

    return merged
