# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is Askloud

Askloud is a natural language search tool for multi-cloud infrastructure inventory (AWS, GCP, Azure). It translates plain English questions into cloud CLI commands or filters local JSON snapshots. The LLM only receives the question and field schema — actual inventory data never leaves the machine.

## Running the Application

### With Docker (recommended)
```bash
export ANTHROPIC_API_KEY=your_key_here

./run_askloud.sh                          # interactive snapshot mode
./run_askloud.sh --live                   # interactive live mode
./run_askloud.sh "list stopped instances" # one-shot query
./run_askloud.sh web-01                   # direct search by name/ID/IP (no LLM)

./run_askloud_collector.sh --schedule          # collect all due resources
./run_askloud_collector.sh --schedule --dry-run
./run_askloud_collector.sh "get ec2 for prod us-east-1"  # NL-driven collection

docker-compose up gui   # web GUI at http://localhost:8000
```

### Without Docker
```bash
pip install anthropic jmespath django
export ANTHROPIC_API_KEY=your_key_here
python3 askloud.py
python3 askloud.py --live
python3 askloud_collector.py --schedule
cd askloud_gui && python manage.py runserver
```

## Required Environment Variables

| Variable | Used by |
|---|---|
| `ANTHROPIC_API_KEY` | Core engine and collector (all LLM calls) |
| `DJANGO_SECRET_KEY` | GUI only |
| `DJANGO_DEBUG` | GUI only (`true`/`false`) |
| `ASKLOUD_BASE_DIR` | GUI: path to project root containing `data/` and `config/` |

Cloud credentials (`~/.aws/`, `~/.azure/`, `~/.config/gcloud`) are mounted read-only in Docker.

## Architecture

### Three Modes
- **Snapshot** (default): queries pre-fetched local JSON in `data/`; no cloud credentials needed at query time
- **Live**: translates question → CLI command → runs locally → renders output; retries up to 2× on error
- **Direct search**: single-token input (name, ID, IP); no LLM call; zero API cost

### Core Engine (`askloud/`)

| File | Role |
|---|---|
| `engine.py` | Main orchestrator: ties loader, LLM, filters, display, history together |
| `loader.py` | Reads JSON from `data/`, injects Account/Region/Provider metadata, builds field schema sent to LLM |
| `collector.py` | Agentic collector: parses NL requests, runs cloud CLIs, saves to `data/` |
| `prompt.py` | Builds system prompt from loaded schema |
| `filters.py` | Direct search, record matching, output filtering |
| `display.py` | Table rendering and per-call token cost tracking |
| `live.py` | Live mode: runs AWS/Azure/GCP CLIs, parses output |
| `settings.py` | Central config: model ID, field aliases, CLI command maps, pricing, ANSI colors |

### Web GUI (`askloud_gui/`)
Django app. `chat/engine_wrapper.py` is the key file — it wraps `CloudInventoryEngine`, intercepts `print_table()` output, returns structured JSON to the frontend, and auto-generates Plotly charts. The engine is initialized once at startup via `chat/apps.py:AppConfig.ready()`.

API endpoints in `chat/views.py`: `/` (index), `/api/query/`, `/api/status/`, `/api/mode/`, `/api/history/`.

### Data Layout
```
data/aws/<AccountName>/<Region>/<resource>.json   # e.g. data/aws/Production/us-east-1/ec2.json
data/azure/<Subscription>/<resource>.json
data/gcp/<Project>/<resource>.json
config/aws/ec2.conf                                # column display config (one field per line)
config/collection_schedule.json                    # what to collect and how often
```

### Extending Resource Types
Add a JSON file under `data/<provider>/.../<resource>.json` and a matching `.conf` file under `config/<provider>/<resource>.conf` listing which fields to display. No code changes needed.

### Field Resolution Order
`loader.py` resolves field names in `.conf` files via: (1) exact JSON key match, (2) alias lookup from `settings.py`, (3) tag key search, (4) recursive leaf search on nested objects.

## No Automated Tests
There are no test files. Verification is manual via CLI and GUI.
