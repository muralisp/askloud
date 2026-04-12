"""
CollectorAgent — fetches cloud resource data via AWS/Azure/GCP CLIs and saves
it to the Askloud data directory in the correct structure.

Usage (standalone):
  python3 askloud_collector.py "get ebs data for production us-east-1"
  python3 askloud_collector.py   # interactive mode
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

import anthropic

from .settings import API_KEY, CLI_TIMEOUT, DATA_DIR

_SCHEDULE_CONFIG = Path("config/collection_schedule.json")


_MODEL_ID = "claude-haiku-4-5-20251001"
_DATA_DIR = Path(DATA_DIR)

_SYSTEM_PROMPT = """\
You are the Askloud Data Collector Agent. You fetch cloud resource data and save
it to the local Askloud data directory using the provider CLIs.

## Data directory structure
  data/aws/<account>/<region>/<resource>.json
  data/azure/<subscription>/<resource>.json
  data/gcp/<project>/<resource>.json

## Workflow
1. Call list_data_directory to see existing account/project/subscription names
2. If the target account/project/subscription does not exist yet, call
   list_cloud_accounts to discover the real name from the cloud provider
3. Construct the correct file_path using the resolved name
4. Call fetch_and_save with provider, args, and file_path
5. Confirm what was saved

## CLI arg patterns (do NOT include the CLI binary name or output flags)

### AWS  (provider: "aws")
  ec2 describe-instances --region <region>
  ec2 describe-volumes --region <region>
  ec2 describe-vpcs --region <region>
  ec2 describe-subnets --region <region>
  ec2 describe-security-groups --region <region>
  ec2 describe-images --owners self --region <region>
  ec2 describe-snapshots --owner-ids self --region <region>
  eks list-clusters --region <region>
  rds describe-db-instances --region <region>
  rds describe-db-clusters --region <region>
  elbv2 describe-load-balancers --region <region>
  lambda list-functions --region <region>
  s3api list-buckets
  iam list-users
  iam list-roles
  cloudwatch describe-alarms --region <region>
  route53 list-hosted-zones

### Azure  (provider: "azure")
  vm list --subscription <subscription>
  vm list-sizes --location <region> --subscription <subscription>
  network vnet list --subscription <subscription>
  network nsg list --subscription <subscription>
  storage account list --subscription <subscription>
  aks list --subscription <subscription>
  sql server list --subscription <subscription>
  disk list --subscription <subscription>
  group list --subscription <subscription>
  keyvault list --subscription <subscription>

### GCP  (provider: "gcp")
  compute instances list --project <project>
  compute disks list --project <project>
  compute networks list --project <project>
  compute firewall-rules list --project <project>
  compute snapshots list --project <project>
  container clusters list --project <project>
  sql instances list --project <project>
  storage buckets list --project <project>
  iam service-accounts list --project <project>
  functions list --project <project>

## Rules
- Always call list_data_directory first to resolve exact account/project names
- Use the exact name from the listing (case-sensitive)
- file_path must start with data/
- For AWS region-specific resources, include the region in both the args and the path
- For Azure and GCP, account name = subscription name or project name respectively
"""

_TOOLS = [
    {
        "name": "list_data_directory",
        "description": (
            "List the existing data directory structure. "
            "Use this to discover exact account/subscription/project names before saving."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_cloud_accounts",
        "description": (
            "Discover available accounts from the cloud provider. "
            "AWS: lists CLI profiles. "
            "Azure: runs 'az account list'. "
            "GCP: runs 'gcloud projects list'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "aws, azure, or gcp"}
            },
            "required": ["provider"],
        },
    },
    {
        "name": "fetch_and_save",
        "description": (
            "Run a cloud CLI command, capture the JSON output, and save it to file_path. "
            "The correct --output/--format json flag is added automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "aws, azure, or gcp",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "CLI arguments without the binary name or output flag. "
                        "e.g. [\"ec2\", \"describe-volumes\", \"--region\", \"us-east-1\"]"
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "Destination path, e.g. data/aws/Production/us-east-1/ebs.json",
                },
            },
            "required": ["provider", "args", "file_path"],
        },
    },
]


class CollectorAgent:
    """
    Agentic data collector: interprets natural language collection requests,
    calls cloud CLIs, and saves JSON output to the data directory.
    """

    def __init__(self):
        self._client      = None   # created lazily — not needed for --schedule mode
        self._session_in  = 0
        self._session_out = 0
        self._llm_calls   = 0
        self._tool_calls  = 0

    @property
    def _llm(self) -> anthropic.Anthropic:
        if self._client is None:
            if not API_KEY:
                print("Error: ANTHROPIC_API_KEY not set.", file=sys.stderr)
                sys.exit(1)
            self._client = anthropic.Anthropic(api_key=API_KEY)
        return self._client

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run_scheduled(self, config_path: Path = _SCHEDULE_CONFIG, dry_run: bool = False):
        """
        Run all due collections defined in the schedule config.
        A resource is due when its file is missing or older than interval_hours.
        """
        schedule = self._load_schedule(config_path)
        resources = schedule.get("resources", [])
        if not resources:
            print("No resources defined in schedule config.")
            return

        now = time.time()
        due, skipped = [], []

        for r in resources:
            fp = Path(r["file_path"])
            interval_secs = float(r.get("interval_hours", 24)) * 3600
            if not fp.exists():
                age_str = "never collected"
                due.append((r, age_str))
            else:
                age_secs = now - fp.stat().st_mtime
                if age_secs >= interval_secs:
                    due.append((r, _fmt_age(age_secs)))
                else:
                    skipped.append((r, _fmt_age(age_secs), _fmt_age(interval_secs - age_secs)))

        print(f"Schedule: {len(due)} due, {len(skipped)} up-to-date")
        if skipped:
            for r, age, remaining in skipped:
                print(f"  \033[90m✓ {r['name']}  (age: {age}, next in: {remaining})\033[0m")
        if not due:
            return

        print()
        errors = 0
        for r, age_str in due:
            print(f"  Collecting: {r['name']}  (age: {age_str})")
            if dry_run:
                print(f"    \033[90m[dry-run] would run: {r['provider']} {' '.join(r['args'])}\033[0m")
                continue
            args = _inject_aws_profile(r["provider"], r["args"], r["file_path"])
            result = self._fetch_and_save(r["provider"], args, r["file_path"])
            if "error" in result:
                print(f"    \033[31mError: {result['error']}\033[0m")
                errors += 1
            else:
                print(f"    \033[32m{result['records']} records → {result['saved']}\033[0m")

        if errors:
            print(f"\n{errors} collection(s) failed.")

    def run(self):
        try:
            if len(sys.argv) > 1:
                self.run_query(" ".join(sys.argv[1:]))
                return

            print("### Askloud Data Collector ###")
            print("Fetch and save cloud resource data from AWS, Azure, and GCP.")
            print()
            print("Examples:")
            print("  get ebs data for production us-east-1")
            print("  download azure vm list for my-subscription")
            print("  fetch gcp compute instances for my-project")
            print("  get rds instances from dev account eu-west-1")
            print()
            print("Type 'exit' to quit.")
            print("-" * 50)

            while True:
                try:
                    query = input("\n> ").strip()
                except EOFError:
                    break
                if query.lower() in ("exit", "quit", "q"):
                    break
                if not query:
                    continue
                self.run_query(query)

        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            if self._llm_calls:
                print(
                    f"\n\033[90mLLM calls: {self._llm_calls} | "
                    f"Tool calls: {self._tool_calls} | "
                    f"Tokens: in={self._session_in:,} out={self._session_out:,}\033[0m"
                )

    def run_query(self, query: str):
        """Run the agent loop for a single user request."""
        messages = [{"role": "user", "content": query}]

        while True:
            response = self._call_llm(messages)
            self._session_in  += response.usage.input_tokens
            self._session_out += response.usage.output_tokens

            tool_uses   = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            for block in text_blocks:
                if block.text.strip():
                    print(block.text)

            if response.stop_reason == "end_turn" or not tool_uses:
                messages.append({"role": "assistant", "content": response.content})
                break

            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in tool_uses:
                self._tool_calls += 1
                print(f"\033[90m  → {block.name}({json.dumps(block.input, separators=(',', ':'))})\033[0m")
                result = self._execute_tool(block.name, block.input)
                if "error" in result:
                    print(f"\033[31m  Error: {result['error']}\033[0m")
                elif "saved" in result:
                    print(f"\033[32m  Saved {result['records']} records → {result['saved']}\033[0m")
                    print(f"\033[90m  Command: {result['command']}\033[0m")
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps(result),
                })

            messages.append({"role": "user", "content": tool_results})

    # ─────────────────────────────────────────────────────────────────────────
    # Tool implementations
    # ─────────────────────────────────────────────────────────────────────────

    def _execute_tool(self, name: str, inputs: dict) -> dict:
        try:
            if name == "list_data_directory":
                return self._list_data_directory()
            if name == "list_cloud_accounts":
                return self._list_cloud_accounts(inputs["provider"])
            if name == "fetch_and_save":
                return self._fetch_and_save(inputs["provider"], inputs["args"], inputs["file_path"])
            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"error": f"Tool error: {e}"}

    def _list_data_directory(self) -> dict:
        tree: dict = {}
        for provider_dir in sorted(_DATA_DIR.iterdir()):
            if not provider_dir.is_dir():
                continue
            provider = provider_dir.name
            tree[provider] = {}
            for root, _, files in os.walk(provider_dir):
                rel   = Path(root).relative_to(_DATA_DIR)
                jsons = [f for f in files if f.endswith(".json")]
                if jsons:
                    tree[provider][str(rel)] = jsons
        return {"structure": tree}

    def _list_cloud_accounts(self, provider: str) -> dict:
        try:
            if provider == "aws":
                profiles: set = set()
                for path in [Path.home() / ".aws" / "credentials", Path.home() / ".aws" / "config"]:
                    if path.exists():
                        for line in path.read_text().splitlines():
                            line = line.strip()
                            if line.startswith("[") and line.endswith("]"):
                                profiles.add(line[1:-1].replace("profile ", ""))
                return {"profiles": sorted(profiles) or ["default"]}

            elif provider == "azure":
                result = subprocess.run(
                    ["az", "account", "list", "--output", "json"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    return {"error": result.stderr[:300]}
                accounts = json.loads(result.stdout)
                return {"subscriptions": [{"name": a["name"], "id": a["id"]} for a in accounts]}

            elif provider == "gcp":
                result = subprocess.run(
                    ["gcloud", "projects", "list", "--format", "json"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    return {"error": result.stderr[:300]}
                projects = json.loads(result.stdout)
                return {"projects": [p.get("projectId") for p in projects]}

            return {"error": f"Unknown provider: {provider}"}
        except FileNotFoundError as e:
            return {"error": f"CLI not found: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def _fetch_and_save(self, provider: str, args: list, file_path: str) -> dict:
        # Validate destination is inside DATA_DIR
        dest = Path(file_path)
        try:
            dest.resolve().relative_to(_DATA_DIR.resolve())
        except ValueError:
            return {"error": f"file_path must be inside {_DATA_DIR}/. Got: {file_path}"}

        provider = provider.lower()
        if provider == "aws":
            cmd = ["aws"] + args + ["--output", "json"]
        elif provider == "azure":
            cmd = ["az"]  + args + ["--output", "json"]
        elif provider == "gcp":
            cmd = ["gcloud"] + args + ["--format", "json"]
        else:
            return {"error": f"Unknown provider '{provider}'. Use: aws, azure, gcp"}

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=CLI_TIMEOUT)
        except FileNotFoundError:
            return {"error": f"CLI not found: '{cmd[0]}'. Is it installed and on PATH?"}
        except subprocess.TimeoutExpired:
            return {"error": f"CLI command timed out after {CLI_TIMEOUT}s"}

        if result.returncode != 0:
            return {"error": result.stderr.strip()[:500] or f"Exit code {result.returncode}"}
        if not result.stdout.strip():
            return {"error": "CLI returned empty output"}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            return {"error": f"CLI output is not valid JSON: {e}\nOutput: {result.stdout[:200]}"}

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w") as fh:
            json.dump(data, fh, indent=2, default=str)

        return {
            "saved":   str(dest),
            "records": self._count_records(data),
            "command": " ".join(cmd),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # LLM call
    # ─────────────────────────────────────────────────────────────────────────

    def _call_llm(self, messages: list):
        self._llm_calls += 1
        return self._llm.messages.create(
            model=_MODEL_ID,
            max_tokens=1024,
            system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=_TOOLS,
            messages=messages,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _count_records(data) -> int:
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    return len(val)
        return 1

    @staticmethod
    def _load_schedule(config_path: Path) -> dict:
        if not config_path.exists():
            print(f"Schedule config not found: {config_path}", file=sys.stderr)
            return {}
        with open(config_path) as fh:
            return json.load(fh)


def _fmt_age(seconds: float) -> str:
    """Format a duration in seconds as a compact human-readable string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}min"
    if seconds < 86400:
        h, m = divmod(seconds, 3600)
        return f"{h}h {m // 60}min" if m >= 60 else f"{h}h"
    d, rem = divmod(seconds, 86400)
    h = rem // 3600
    return f"{d}d {h}h" if h else f"{d}d"


def _inject_aws_profile(provider: str, args: list, file_path: str) -> list:
    """Auto-append --profile <account> for AWS commands when not already present."""
    if provider.lower() != "aws" or "--profile" in args:
        return args
    parts = Path(file_path).parts
    try:
        # Layout: data / aws / <account> / <region> / ...
        idx = list(parts).index("aws")
        account = parts[idx + 1]
        return args + ["--profile", account]
    except (ValueError, IndexError):
        return args
