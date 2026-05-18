# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Askloud is a conversational cloud inventory tool. Users ask questions in plain English; the engine translates them into either a JSON query plan (inventory mode, against DynamoDB or local JSON files) or CLI commands (live mode, run locally). The LLM only ever receives the user's question — inventory data never leaves the machine.

## Commands

```bash
# Run the CLI
python3 askloud.py                        # inventory mode (interactive)
python3 askloud.py --live                 # live mode (interactive)
python3 askloud.py "list stopped ec2"     # one-shot query

# Run the data collector
python3 askloud_collector.py --schedule   # run overdue collections
python3 askloud_collector.py --schedule --dry-run

# Run the Django GUI
cd askloud_gui && python manage.py runserver   # http://localhost:8000

# Docker (recommended)
./run_askloud.sh               # inventory CLI
./run_askloud.sh --live        # live CLI
docker-compose up gui          # web GUI

# Tests (tests live in scripts.bak/tests/)
cd scripts.bak && pytest tests/                     # all tests
cd scripts.bak && pytest tests/test_engine.py -k "test_finds_by_instance_id"

# Ops / maintenance
python3 ops/reconcile_inventory.py --dry-run        # soft-delete stale DynamoDB records
python3 terraform/askloud_ingest.py --bucket askloud-tfstate --prefix dev/ --dry-run

# Deploy to Kubernetes
ANTHROPIC_API_KEY=... ./deploy-eks.sh dev    # AWS EKS
./deploy-aks.sh dev                          # Azure AKS
./deploy-gke.sh dev                          # GCP GKE
```

**Required env var:** `ANTHROPIC_API_KEY`

**Key optional env vars:** `ASKLOUD_DYNAMODB_TABLE`, `ASKLOUD_DYNAMODB_REGION`, `ASKLOUD_DYNAMODB_PROFILE`, `ASKLOUD_ACCOUNT_ALIASES` (JSON map of account-id → friendly-name), `ASKLOUD_QUERY_CACHE_TTL` (seconds, default 60).

**Dependencies:** `pip install anthropic jmespath` (CLI); add `django whitenoise gunicorn` for the GUI.

## Architecture

### Core Engine Flow (inventory mode)

```
askloud.py
  └─ CloudInventoryEngine (askloud/engine.py)
       ├─ DataLoader (askloud/loader.py)      — reads data/ and config/
       ├─ build_system_prompt (askloud/prompt.py) — assembles LLM context from loader state
       ├─ is_direct_search (askloud/filters.py)   — single-token → bypass LLM
       ├─ execute_plan()                       — runs the LLM's JSON plan against loader.data
       ├─ execute_refresh() (askloud/refresh.py)  — live CLI fetch → merge into loader
       └─ print_table / CostTracker (askloud/display.py)
```

**Inventory query lifecycle:**
1. `DataLoader` walks `data/` and `config/`, enriches records with `Account`/`Region`/`Provider` from the directory path, builds jmespath field maps.
2. `build_system_prompt` sends only field schemas and file paths to the LLM (never actual data).
3. LLM returns a JSON plan with `steps[]`, each specifying a resource, filters, and columns.
4. `execute_plan` runs jmespath filters from `askloud/filters.py` locally and renders a table.

**DynamoDB mode:** When `ASKLOUD_DYNAMODB_TABLE` is set, `engine.py` bypasses local JSON files. At startup, `dynamo.py:load_schema_samples()` fetches one sample record per resource type (schema only). Per-query, `dynamo.py:query_resource()` fetches full records using `PK = aws#ACCOUNT_ID#RESOURCE_TYPE` key queries. Results are cached in-process for `ASKLOUD_QUERY_CACHE_TTL` seconds.

**Live mode** (`askloud/live.py`): one LLM call translates the question into CLI commands; engine runs them locally via subprocess. Cloud output never reaches the LLM (only error messages on failure for retry).

**Agentic Terraform mode** (`askloud/terraform_change.py`): supports `set_tag`, `remove_tag`, `create_resource`, and `delete_resource`. Reads tfstate from S3, resolves the Terraform resource address, edits `.tf` files or renders HCL templates from `askloud/tf_templates.py`, runs `terraform plan` for user confirmation, then applies. The diff lambda (`terraform/diff_lambda.py`) picks up the new tfstate and updates DynamoDB automatically.

**TUI:** When a query returns 2+ result tables and stdout is a tty, `askloud/tui.py` launches a Textual tab-based viewer (press `q` to exit).

### Data & Config Layout

```
data/
  aws/<AccountName>/<region>/<resource>.json   # e.g. data/aws/Production/us-east-1/ec2.json
  gcp/vm.json
  azure/vm.json

config/
  aws/ec2.conf   vpc.conf   subnet.conf   ebs.conf ...
  gcp/gce.conf
  azure/vm.conf
  collection_schedule.json    # per-resource collection intervals
  terraform_workspaces.json   # workspace → S3 tfstate mapping
```

`.conf` files list display column names (one per line). `DataLoader.build_field_maps_for()` resolves these names through: explicit jmespath → global alias → resource alias → top-level field → tag key → recursive leaf search. Adding/removing a line changes query output with no code changes.

### Model & Settings

All tunables are in `askloud/settings.py`: `MODEL_ID` (default `claude-haiku-4-5-20251001`), `MAX_HISTORY_TURNS` (10), `MAX_LIVE_RETRIES` (2), `FIELD_ALIASES`, `DEDUP_FIELDS`, `NOISE_TAG_PREFIXES`. The system prompt is cached via Anthropic's prompt caching (`cache_control: ephemeral`).

Adding a new AWS resource type requires: a `.conf` file under `config/aws/`, entries in `FIELD_ALIASES` and `DEDUP_FIELDS` in `settings.py`, and entries in `_ENGINE_TO_TF` / `_RESOURCE_TYPE_MAP` in `terraform_change.py` / `dynamo.py`.

### Ingestion Pipeline (DynamoDB)

```
S3 tfstate write
  → EventBridge rule
    → diff_lambda.py         — diffs tfstate vs DynamoDB, emits UPSERT/DELETE to SQS
      → router_lambda.py     — routes SQS messages to the inventory table
        → askloud_ingest.py  — bootstrap/manual trigger (bypasses Lambda)
```

`ec2_events_lambda.py` handles real-time EC2 state-change events (start/stop) so the inventory reflects actual instance state between tfstate snapshots.

`ops/reconcile_inventory.py` soft-deletes DynamoDB records with no matching resource in any current tfstate (uses `config/terraform_workspaces.json` as the workspace manifest).

### Django GUI (`askloud_gui/`)

`chat/engine_wrapper.py` (`EngineManager`) is a singleton that owns a `CloudInventoryEngine`. It patches `print_table` to capture structured table data (headers/rows) instead of printing to stdout, then optionally generates a Plotly chart spec. `chat/views.py` serves these as JSON; the frontend renders tables and pie/bar charts.

### CI/CD

Every push to `main` → GitHub Actions (`.github/workflows/deploy.yml`):
1. OIDC auth → short-lived AWS credentials (no stored secrets)
2. Build both Docker images (`askloud-engine`, `askloud-gui`) → push to ECR with short SHA tag
3. `yq` updates `helm/askloud-gui/values.yaml` with the new tag → committed back with `[skip ci]`
4. ArgoCD detects the values.yaml change and rolls out automatically

`v*` tags promote to prod instead of dev.

### Terraform

`terraform/` has a modular structure: `_modules/` (aws fully implemented; azure/gcp are scaffolds), `_policies/` (OPA/Conftest tag enforcement, per-cloud tflint/checkov config), `dev/aws/` and `prod/aws/` (active). Azure/GCP environments are scaffold only.
