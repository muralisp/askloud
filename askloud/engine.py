"""
CloudInventoryEngine — main orchestrator.

Ties together DataLoader, prompt builder, LLM client, filters, display, and
refresh into the public-facing interface used by the entry point scripts.
"""

import os
import sys
import json
import re
import time
import anthropic
try:
    import readline  # noqa: F401 — enables arrow-key history in input()
except ImportError:
    pass  # not available on Windows; degrade silently

from .settings  import API_KEY, MODEL_ID, MAX_HISTORY_TURNS, MAX_LIVE_RETRIES, PROVIDER_COLORS, ANSI_RESET, PROMPT_MODE_COLOR, PROMPT_ASK_COLOR
from .loader    import DataLoader
from .prompt    import build_system_prompt
from .filters   import is_direct_search, record_match_evidence, apply_filters, cell
from .display   import print_table, CostTracker
from .refresh   import execute_refresh
from .live      import get_aws_profiles, build_live_system_prompt, execute_live_plan

MODE_SNAPSHOT = "snapshot"
MODE_LIVE     = "live"


class CloudInventoryEngine:

    def __init__(self, mode: str = MODE_SNAPSHOT):
        self._llm_client: anthropic.Anthropic = None   # created lazily
        self.history: list  = []
        self._is_retry      = False
        self.mode           = mode

        self._loader        = DataLoader()
        self._cost          = CostTracker()

        print("\033[90mLoading inventory data...\033[0m")
        self._loader.load_configs()
        self._loader.load_data()
        self._loader.extract_schemas()
        self._loader.build_field_maps()
        self.system_prompt = build_system_prompt(self._loader)

        self._live_profiles      = get_aws_profiles()
        self._live_system_prompt = build_live_system_prompt(self._live_profiles)

        print("\033[90mReady.\033[0m\n")

    # ─────────────────────────────────────────────────────────────────────────
    # Direct search (no LLM call)
    # ─────────────────────────────────────────────────────────────────────────

    def direct_search(self, term: str) -> bool:
        """
        Search all loaded records for term (case-insensitive).
        Displays config columns plus a 'Matched' column showing which field matched.
        Returns True if any results were found.
        """
        term_lower  = term.lower()
        found_any   = False
        loader      = self._loader

        for rt in sorted(loader.data):
            hits = []
            for r in loader.data[rt]:
                evidence = record_match_evidence(r, term_lower)
                if evidence:
                    label, val = evidence
                    display = f"{label}={val[:40]}" if len(val) > 40 else f"{label}={val}"
                    hits.append((r, display))
            if not hits:
                continue

            fmap          = loader.field_maps.get(rt, {})
            config_fields = loader.configs.get(rt, [])
            meta          = loader.populated_meta.get(rt, set())
            columns = [
                (fname, fmap[fname])
                for fname in config_fields
                if fname in fmap
                and (fname not in ("Account", "Region") or fname in meta)
            ]
            if not columns:
                from .settings import DEDUP_FIELDS
                fallback = [f for f in (DEDUP_FIELDS.get(rt),) if f]
                fallback += [f for f in ("Account", "Region") if f in meta]
                columns = [(f, f) for f in fallback]

            headers = [c[0] for c in columns] + ["Matched"]
            rows    = [
                [cell(r, c[1]) for c in columns] + [label]
                for r, label in hits
            ]
            provider = hits[0][0].get("Provider") if hits else self._provider_for(rt)
            print_table(f"[{rt}] {term}", headers, rows, provider=provider)
            print()
            found_any = True

        if not found_any:
            print(f"\033[33mNo results found for '{term}'.\033[0m")

        self._cost.record_direct_search()
        return found_any

    # ─────────────────────────────────────────────────────────────────────────
    # Query plan execution
    # ─────────────────────────────────────────────────────────────────────────

    def execute_plan(self, plan: dict) -> bool:
        """Execute a parsed query plan and print results. Returns True if anything was shown."""
        if plan.get("unavailable"):
            title = plan.get("title", "")
            if title:
                print(f"\033[33m{title}\033[0m")
            print(f"\033[33m{plan['unavailable']}\033[0m")
            return True

        bindings    = {}
        first_shown = True
        loader      = self._loader

        for step in plan.get("steps", []):
            # Refresh step — fetch live data, merge, rebuild prompt
            if step.get("action") == "refresh":
                step = _interpolate_bindings(step, bindings)
                if execute_refresh(step, loader):
                    self.system_prompt = build_system_prompt(loader)
                first_shown = False
                continue

            resource = step.get("resource")
            if resource not in loader.data:
                print(f"\033[31mUnknown resource '{resource}'. Available: {', '.join(sorted(loader.data))}\033[0m")
                continue

            records = apply_filters(list(loader.data[resource]), step, bindings)
            self._cost.record_result_tokens(records)

            # When filters produce no results, tell the user what IS available
            # in the snapshot for this resource type so they know whether to use /live.
            if not records and not step.get("bind") and step.get("show", True):
                all_of_type = loader.data.get(resource, [])
                title = plan.get("title", resource) if first_shown else f"[{resource}]"
                if all_of_type:
                    accounts = sorted({r.get("Account", "") for r in all_of_type if r.get("Account")})
                    regions  = sorted({r.get("Region",  "") for r in all_of_type if r.get("Region")})
                    parts = []
                    if accounts:
                        parts.append("accounts: " + ", ".join(accounts))
                    if regions:
                        parts.append("regions: " + ", ".join(regions))
                    hint = f"Snapshot has {resource} data for {'; '.join(parts)}." if parts else f"Snapshot has {resource} data, but none matched."
                    print(f"\033[33m{title} — no results.\033[0m")
                    print(f"\033[33m{hint}  Use /live to query other accounts in real time.\033[0m\n")
                else:
                    print(f"\033[33m{title} — no {resource} data in snapshot.  Use /live to fetch it.\033[0m\n")
                first_shown = False
                continue

            if step.get("bind") and records:
                for var_name, path in step["bind"].items():
                    bindings[var_name] = cell(records[0], path, default="")

            if not step.get("show", True):
                continue

            if step.get("count_only"):
                title = plan.get("title", resource) if first_shown else f"[{resource}]"
                print(f"\033[33m{title}\033[0m")
                print(f"{len(records):,} {resource} record{'s' if len(records) != 1 else ''} match.")
                print()
                first_shown = False
                continue

            columns = step.get("columns") or []
            if not columns:
                continue

            # Drop Account/Region columns for resources where they aren't populated
            meta    = loader.populated_meta.get(resource, set())
            columns = [c for c in columns if c["header"] not in ("Account", "Region") or c["header"] in meta]

            # Guardrail: always show every field used as a filter criterion
            existing_headers = {c["header"].lower() for c in columns}
            sample = loader.data.get(resource, [{}])[0]
            uses_dict_tags = isinstance(sample.get("tags"), dict) and not isinstance(sample.get("Tags"), list)

            for field in (step.get("icontains") or {}):
                if field.lower() not in existing_headers:
                    columns.append({"header": field, "path": field, "default": "N/A"})
                    existing_headers.add(field.lower())

            for tag_key in list(step.get("tag_icontains") or {}) + list(step.get("tag_equals") or {}):
                if tag_key.lower() not in existing_headers:
                    path = (f"tags.{tag_key}" if uses_dict_tags
                            else f"Tags[?Key=='{tag_key}'].Value | [0]")
                    columns.append({"header": tag_key, "path": path, "default": "N/A"})
                    existing_headers.add(tag_key.lower())

            headers = [col["header"] for col in columns]
            rows    = [
                [cell(r, col["path"], col.get("default", "N/A")) for col in columns]
                for r in records
            ]

            title    = plan.get("title", "") if first_shown else f"[{resource}]"
            provider = records[0].get("Provider") if records else self._provider_for(resource)
            print_table(title, headers, rows, provider=provider)
            first_shown = False
            print()

        return not first_shown

    # ─────────────────────────────────────────────────────────────────────────
    # LLM interaction
    # ─────────────────────────────────────────────────────────────────────────

    def process_query(self, user_query: str) -> bool:
        """Route the query to snapshot or live processing based on current mode."""
        if self.mode == MODE_LIVE:
            return self._process_live_query(user_query)
        return self._process_snapshot_query(user_query)

    def _process_snapshot_query(self, user_query: str) -> bool:
        """Snapshot mode: translate query to a JSON plan and execute against local data."""
        self.history.append({"role": "user", "content": user_query})
        self._trim_history()

        try:
            response = self._call_llm()

            while True:
                label          = "retry" if self._is_retry else ""
                self._is_retry = False
                self._cost.record_llm_usage(response.usage, label=label)

                raw = response.content[0].text.strip()
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$",       "", raw).strip()

                self.history.append({"role": "assistant", "content": raw})

                try:
                    plan = json.loads(raw)
                except json.JSONDecodeError as e:
                    print(f"\033[31mLLM returned invalid JSON: {e}\033[0m")
                    self.history.append({
                        "role":    "user",
                        "content": f"Your response was not valid JSON ({e}). Return only a raw JSON object.",
                    })
                    self._trim_history()
                    self._is_retry = True
                    response = self._call_llm()
                    continue

                self.execute_plan(plan)
                return True

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    def _process_live_query(self, user_query: str) -> bool:
        """
        Live mode: NL → CLI plan (single LLM call) → engine runs commands locally → table.

        If all commands fail, the error messages (not cloud data) are fed back to the LLM
        so it can try alternative profiles or commands. Retries up to MAX_LIVE_RETRIES times.
        Cloud data never reaches the LLM.
        """
        messages = [{"role": "user", "content": user_query}]

        try:
            for attempt in range(MAX_LIVE_RETRIES + 1):
                response = self._llm.messages.create(
                    model=MODEL_ID,
                    max_tokens=2048,
                    system=[{
                        "type": "text",
                        "text": self._live_system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=messages,
                )
                self._cost.record_llm_usage(response.usage)

                raw = response.content[0].text.strip()
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$",       "", raw).strip()

                try:
                    plan, _ = json.JSONDecoder().raw_decode(raw)
                except json.JSONDecodeError as e:
                    print(f"\033[31mLLM returned invalid JSON: {e}\033[0m")
                    return False

                # Print commands before running them
                cmds = plan.get("commands", [])
                if cmds:
                    print("\033[90mCommand(s) used:\033[0m")
                    for cmd_spec in cmds:
                        print(f"\033[90m  {_build_cmd_str(cmd_spec)}\033[0m")
                    print()

                # Run CLI commands locally — results never leave the machine
                records, errors, injected_keys = execute_live_plan(plan)

                # Got results (even with some partial errors) — render and done
                if records:
                    for err in errors:
                        print(f"\033[33mWarning: {err}\033[0m")

                    # Auto-prepend columns for any injected flag whose value varies
                    # across the result set (e.g. profile differs → add Profile column)
                    varying = [
                        k for k in injected_keys
                        if len({r.get(k, "") for r in records}) > 1
                    ]
                    extra_cols = [
                        {"header": k.capitalize(), "path": k, "default": ""}
                        for k in sorted(varying)
                    ]
                    columns = extra_cols + plan.get("columns", [])

                    headers = [c["header"] for c in columns]
                    rows    = [
                        [cell(r, c["path"], c.get("default", "N/A")) for c in columns]
                        for r in records
                    ]
                    title    = plan.get("title", "")
                    provider = plan.get("provider", "aws")
                    print_table(title, headers, rows, provider=provider)
                    print()
                    return True

                # All commands failed — feed errors back for a retry
                if errors and attempt < MAX_LIVE_RETRIES:
                    error_summary = "\n".join(errors)
                    print(f"\033[33mRetrying ({attempt + 1}/{MAX_LIVE_RETRIES})...\033[0m\n")
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({
                        "role":    "user",
                        "content": (
                            f"All commands failed with these errors:\n{error_summary}\n\n"
                            "Please try alternative profiles, regions, or commands."
                        ),
                    })
                    continue

                # No records, no retries left
                for err in errors:
                    print(f"\033[31mError: {err}\033[0m")
                if not errors:
                    print("\033[33mNo results returned.\033[0m")
                return True

        except KeyboardInterrupt:
            print("\n[interrupted]")
            return True
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(self):
        try:
            if len(sys.argv) > 1:
                query = " ".join(sys.argv[1:])
                if self.mode == MODE_SNAPSHOT and is_direct_search(query):
                    self.direct_search(query)
                else:
                    self.process_query(query)
                return

            self._print_header()

            while True:
                try:
                    prompt = self._make_prompt()
                    user_query = input(prompt).strip()
                except EOFError:
                    break
                if user_query.lower() in ("exit", "quit", "q"):
                    break
                if not user_query:
                    continue

                _cmd = user_query.lower()
                if _cmd == "/live":
                    self._switch_mode(MODE_LIVE)
                    continue
                if _cmd in ("/snapshot", "/snap"):
                    self._switch_mode(MODE_SNAPSHOT)
                    continue
                if _cmd in ("/mode", "/?"):
                    print(f"Current mode: {self.mode}  (switch with /live or /snapshot)")
                    continue
                if _cmd.startswith("/"):
                    print(f"Unknown command '{user_query}'. Available: /live  /snapshot  /snap  /mode  !<shell>")
                    continue

                if user_query.startswith("!"):
                    _run_shell(user_query[1:].strip())
                    continue

                if " | " in user_query:
                    nl_part, pipe_part = user_query.split(" | ", 1)
                    self._run_with_pipe(nl_part.strip(), pipe_part.strip())
                    continue

                if self.mode == MODE_SNAPSHOT and is_direct_search(user_query):
                    self.direct_search(user_query)
                else:
                    self.process_query(user_query)

        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            self._cost.print_session_summary(system_prompt=self.system_prompt)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _print_header(self):
        print("### Askloud — Cloud Inventory Chat Engine ###")
        print(f"Mode: {self.mode}  |  Resources: {', '.join(sorted(self._loader.data))}")
        if self.mode == MODE_SNAPSHOT:
            age = self._snapshot_age_str()
            age_info = f"  |  Snapshot: {age} old" if age else ""
            print(f"Single-token input → direct search (no LLM).{age_info}")
        else:
            print(f"Live mode — {len(self._live_profiles)} AWS profiles available.")
        print("Commands: /live  /snapshot  /mode  !<shell cmd>  exit")
        print("-" * 50)

    def _make_prompt(self) -> str:
        if self.mode == MODE_SNAPSHOT:
            age = self._snapshot_age_str()
            label = f"snapshot: {age} old" if age else "snapshot"
        else:
            label = self.mode
        return f"\n{PROMPT_MODE_COLOR}[{label}]{ANSI_RESET} {PROMPT_ASK_COLOR}Ask >{ANSI_RESET} "

    def _snapshot_age_str(self) -> str:
        """Return the age of the oldest loaded data file as a compact string, e.g. '6h', '2d 4h'."""
        oldest = None
        for sources in self._loader.file_sources.values():
            for src in sources:
                p = src.get("file_path", "")
                if p and os.path.exists(p):
                    mtime = os.path.getmtime(p)
                    if oldest is None or mtime < oldest:
                        oldest = mtime
        if oldest is None:
            return ""
        age = int(time.time() - oldest)
        if age < 3600:
            return f"{age // 60}min"
        if age < 86400:
            h, m = divmod(age, 3600)
            return f"{h}h {m // 60}min" if m >= 60 else f"{h}h"
        d, rem = divmod(age, 86400)
        h = rem // 3600
        return f"{d}d {h}h" if h else f"{d}d"

    def _switch_mode(self, new_mode: str):
        if new_mode == self.mode:
            print(f"Already in {self.mode} mode.")
            return
        self.mode    = new_mode
        self.history = []   # clear snapshot history on switch
        print(f"\033[33mSwitched to {new_mode} mode.\033[0m")

    def _call_llm(self):
        return self._llm.messages.create(
            model=MODEL_ID,
            max_tokens=2048,
            system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=self.history,
        )

    @property
    def _llm(self) -> anthropic.Anthropic:
        if self._llm_client is None:
            if not API_KEY:
                print("Error: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
                sys.exit(1)
            self._llm_client = anthropic.Anthropic(api_key=API_KEY)
        return self._llm_client

    def _trim_history(self):
        max_messages = MAX_HISTORY_TURNS * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

    def _provider_for(self, rt: str) -> str:
        """Return the provider string for a resource type by inspecting its records."""
        records = self._loader.data.get(rt, [])
        return records[0].get("Provider", "aws") if records else "aws"

    def _run_with_pipe(self, nl_query: str, pipe_cmd: str):
        """
        Execute a NL query, capture its stdout, then pipe the captured text through
        a shell pipeline.  The full chain after the first ' | ' is passed to the shell,
        so multi-segment pipes like 'grep foo | wc -l' work correctly.
        """
        import io
        import contextlib
        import subprocess

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            if self.mode == MODE_SNAPSHOT and is_direct_search(nl_query):
                self.direct_search(nl_query)
            else:
                self.process_query(nl_query)

        result = subprocess.run(
            pipe_cmd, shell=True, input=buf.getvalue(), text=True, capture_output=True
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)


def _build_cmd_str(inputs: dict) -> str:
    """Build a copy-pasteable CLI string from a run_cli tool input."""
    from .live import _CLI_BINARY, _OUTPUT_FLAGS
    provider = inputs.get("provider", "aws").lower()
    args     = [str(a) for a in inputs.get("args", [])]
    cli      = _CLI_BINARY.get(provider, provider)
    flags    = _OUTPUT_FLAGS.get(provider, [])
    return " ".join([cli] + args + flags)


def _run_shell(cmd: str):
    """Execute a shell command and stream its output to stdout/stderr."""
    if not cmd:
        return
    import subprocess
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def _interpolate_bindings(step: dict, bindings: dict) -> dict:
    """Replace {var} placeholders in refresh step args, file_path, and scope."""
    if not bindings:
        return step
    step = dict(step)
    if step.get("args"):
        step["args"] = [
            s.format(**bindings) if isinstance(s, str) else s
            for s in step["args"]
        ]
    if step.get("file_path") and isinstance(step["file_path"], str):
        step["file_path"] = step["file_path"].format(**bindings)
    if step.get("scope") and isinstance(step["scope"], dict):
        step["scope"] = {
            k: v.format(**bindings) if isinstance(v, str) else v
            for k, v in step["scope"].items()
        }
    return step
