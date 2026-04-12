"""
Terminal display: table rendering and cost/token tracking.

  print_table(title, headers, rows, provider)  — formatted table with provider-branded header
  CostTracker                                  — accumulates token counts; prints per-call usage
                                                 and a session summary with savings breakdown
"""

import sys
from .settings import PROVIDER_COLORS, ANSI_RESET, TOKEN_PRICES, MODEL_ID


def print_table(title: str, headers: list, rows: list, provider: str = None):
    color = PROVIDER_COLORS.get(provider or "aws", PROVIDER_COLORS["aws"])
    if title:
        print(f"\033[33m{title}\033[0m")
    if not rows:
        print("\033[33mNo results found.\033[0m")
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(c))
    sep = "  "
    header_str = sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(f"{color}{header_str}{ANSI_RESET}")
    for row in rows:
        print(sep.join(c.ljust(widths[i]) for i, c in enumerate(row)))


class CostTracker:
    """
    Accumulates token usage across LLM calls and direct searches.
    Reports per-call cost inline and a full savings breakdown at session end.
    """

    def __init__(self):
        self._session_in          = 0
        self._session_out         = 0
        self._session_cache_write = 0
        self._session_cache_read  = 0
        self._query_count         = 0
        self._direct_search_count = 0
        self._result_data_tokens  = 0   # estimated tokens in data returned by execute_plan

    # ── Public interface ─────────────────────────────────────────────────────

    def record_llm_usage(self, usage, label: str = ""):
        """Update counters and print a one-line cost summary for this call."""
        tin = usage.input_tokens
        tout = usage.output_tokens
        tcw  = getattr(usage, "cache_creation_input_tokens", 0) or 0
        tcr  = getattr(usage, "cache_read_input_tokens",     0) or 0

        self._session_in          += tin
        self._session_out         += tout
        self._session_cache_write += tcw
        self._session_cache_read  += tcr
        self._query_count         += 1

        prices    = TOKEN_PRICES.get(MODEL_ID, {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0})
        call_cost = (
            tin  * prices["input"]
            + tout * prices["output"]
            + tcw  * prices.get("cache_write", 0)
            + tcr  * prices.get("cache_read",  0)
        ) / 1_000_000
        sess_cost = (
            self._session_in          * prices["input"]
            + self._session_out         * prices["output"]
            + self._session_cache_write * prices.get("cache_write", 0)
            + self._session_cache_read  * prices.get("cache_read",  0)
        ) / 1_000_000

        tag        = f" [{label}]" if label else ""
        cache_info = ""
        if tcw:
            cache_info += f" cache_write={tcw:,}"
        if tcr:
            cache_info += f" cache_read={tcr:,}"
        print(
            f"\033[90m[tokens{tag}: in={tin:,} out={tout:,}{cache_info} | "
            f"call=${call_cost:.4f} | "
            f"session: in={self._session_in:,} out={self._session_out:,} total=${sess_cost:.4f}]\033[0m"
        )

    def record_direct_search(self):
        """Count one query answered without an LLM call."""
        self._direct_search_count += 1

    def record_result_tokens(self, records: list):
        """Accumulate estimated token size of query result records (4 chars ≈ 1 token)."""
        import json
        for r in records:
            self._result_data_tokens += len(json.dumps(r)) // 4

    def print_session_summary(self, system_prompt: str = ""):
        if self._query_count == 0 and self._direct_search_count == 0:
            return
        prices = TOKEN_PRICES.get(MODEL_ID, {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0})
        total = (
            self._session_in          * prices["input"]
            + self._session_out         * prices["output"]
            + self._session_cache_write * prices.get("cache_write", 0)
            + self._session_cache_read  * prices.get("cache_read",  0)
        ) / 1_000_000

        # 1. Prompt cache savings: avoided paying full input price for cached tokens
        cache_saved = (
            self._session_cache_read * (prices["input"] - prices.get("cache_read", 0))
        ) / 1_000_000

        # 2. Direct search savings: each bypassed one LLM round-trip
        if self._query_count > 0:
            avg_call_cost = total / self._query_count
        else:
            # No LLM calls at all — estimate from system prompt size
            avg_call_cost = (len(system_prompt) // 4) * prices["input"] / 1_000_000
        direct_saved = self._direct_search_count * avg_call_cost

        # 3. Local data execution savings: LLM returned a compact query plan, not raw data
        data_saved = max(0, self._result_data_tokens - self._session_out) * prices["output"] / 1_000_000

        total_saved = cache_saved + direct_saved + data_saved

        lines = [
            f"\n\033[90m── Session summary ──",
            f"  LLM calls   : {self._query_count}",
            f"  Input       : {self._session_in:,} tokens",
            f"  Output      : {self._session_out:,} tokens",
        ]
        if self._session_cache_write:
            lines.append(f"  Cache write : {self._session_cache_write:,} tokens")
        if self._session_cache_read:
            lines.append(f"  Cache read  : {self._session_cache_read:,} tokens")
        lines.append(f"  Total cost  : ${total:.4f}  (model: {MODEL_ID})")
        lines.append("")
        lines.append("── Estimated savings ──")
        if self._session_cache_read:
            lines.append(f"  Prompt cache        : ${cache_saved:.4f}  ({self._session_cache_read:,} tokens read from cache)")
        if self._direct_search_count:
            lines.append(f"  Direct search       : ${direct_saved:.4f}  ({self._direct_search_count} LLM call(s) avoided)")
        lines.append(
            f"  Local data execution: ${data_saved:.4f}"
            f"  (~{self._result_data_tokens:,} result tokens never sent to LLM)"
        )
        lines.append(f"  Total saved         : ${total_saved:.4f}\033[0m")
        print("\n".join(lines))
