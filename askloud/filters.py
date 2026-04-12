"""
Stateless filter utilities used during query plan execution and direct search.
No imports from this package — only stdlib and jmespath.
"""

import jmespath
import jmespath.exceptions


def is_direct_search(query: str) -> bool:
    """Return True if the query is a single token (no whitespace) — triggers direct search."""
    return bool(query) and not any(c.isspace() for c in query)


def cell(record: dict, path: str, default: str = "N/A") -> str:
    """Extract one display cell value from a record using jmespath."""
    try:
        val = jmespath.search(path, record)
        return str(val) if val is not None else default
    except jmespath.exceptions.JMESPathError:
        return default


def record_match_evidence(record: dict, term_lower: str):
    """
    Return (display_label, matched_value) for the first field/tag that contains
    term_lower (case-insensitive), or None if no match.
    Searches top-level strings, one level of nested-dict strings, and tag values.
    """
    for key, val in record.items():
        if key == "Tags":
            continue
        if isinstance(val, str) and term_lower in val.lower():
            return (key, val)
        if isinstance(val, dict):
            for sub_key, sub_val in val.items():
                if isinstance(sub_val, str) and term_lower in sub_val.lower():
                    return (f"{key}.{sub_key}", sub_val)
    for t in (record.get("Tags") or []):
        if isinstance(t, dict):
            k = t.get("Key", "")
            v = t.get("Value", "")
            if isinstance(v, str) and term_lower in v.lower():
                return (f"Tag:{k}", v)
    return None


def apply_filters(records: list, step: dict, bindings: dict) -> list:
    """
    Apply all filter conditions from a query plan step and return matching records.

    Supports:
      filter        — jmespath expression with optional {var} interpolation from bindings
      icontains     — case-insensitive substring match on top-level fields
      tag_icontains — case-insensitive substring match on tag values (AWS array + Azure dict)
      tag_equals    — exact match on tag values (AWS array + Azure dict)
      dedupe_field  — deduplicate results by a named field
    """
    filter_expr = step.get("filter")
    if filter_expr:
        try:
            filter_expr = filter_expr.format(**bindings)
            result = jmespath.search(filter_expr, records)
            if result is None:
                records = []
            elif isinstance(result, dict):
                records = [result]
            else:
                records = [r for r in result if isinstance(r, dict)]
        except (jmespath.exceptions.JMESPathError, KeyError) as e:
            print(f"\033[31mjmespath error: {e}\033[0m")
            return []

    for field, substring in (step.get("icontains") or {}).items():
        sub = substring.lower()
        records = [r for r in records if sub in str(r.get(field, "")).lower()]

    for tag_key, substring in (step.get("tag_icontains") or {}).items():
        sub = substring.lower()
        records = [r for r in records if _tag_match(r, tag_key, lambda v: sub in v.lower())]

    for tag_key, value in (step.get("tag_equals") or {}).items():
        records = [r for r in records if _tag_match(r, tag_key, lambda v: v == value)]

    dedupe_field = step.get("dedupe_field")
    if dedupe_field:
        seen, deduped = set(), []
        for r in records:
            key = r.get(dedupe_field)
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        records = deduped

    return records


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _tag_match(record: dict, tag_key: str, predicate) -> bool:
    """Return True if any matching tag value satisfies predicate(value)."""
    # AWS array format: Tags: [{Key, Value}, ...]
    for t in (record.get("Tags") or []):
        if isinstance(t, dict) and t.get("Key") == tag_key:
            if predicate(str(t.get("Value", ""))):
                return True
    # Azure dict format: tags: {Key: Value, ...}
    azure_tags = record.get("tags")
    if isinstance(azure_tags, dict):
        val = azure_tags.get(tag_key)
        if val is not None and predicate(str(val)):
            return True
    return False
