# Askloud

A conversational search tool for querying multi-cloud infrastructure inventory across AWS, GCP, and Azure — no query language required.

Ask in plain English. Get a formatted table. Your inventory data never leaves your machine.

---

## Features

- **Two modes** — *snapshot* queries local JSON exports instantly (offline, zero CLI calls); *live* translates your question to cloud CLI commands and runs them in real time
- **Natural language queries** — powered by Claude (Anthropic), translated into structured query plans or CLI commands executed locally
- **Direct search** — single-token input (name, ID, IP) bypasses the LLM entirely; zero token cost
- **Multi-cloud** — unified interface across AWS, GCP, and Azure
- **Privacy by design** — in both modes the LLM receives only your question; actual inventory data and CLI output stay on your machine
- **Shell integration** — prefix `!` to run any shell command; append `| cmd` to pipe query output through it
- **Automated collection** — schedule-driven data collector keeps your snapshot fresh
- **Docker-ready** — ships with a Dockerfile and wrapper scripts; all cloud CLIs included

---

## Quick Start (Docker — recommended)

Docker is the easiest way to get started. No Python setup, no CLI installations — everything is bundled in the image.

**Prerequisites:** Docker installed, an [Anthropic API key](https://console.anthropic.com/), and cloud credentials configured on your host (`aws configure`, `az login`, `gcloud auth login`).

```bash
# 1. Build the image (one-time)
docker build -t askloud:latest .

# 2. Set your API key
export ANTHROPIC_API_KEY=your_key_here

# 3. Run
./run_askloud.sh               # interactive snapshot mode
./run_askloud.sh --live        # interactive live mode
./run_askloud.sh "list stopped instances in production"
./run_askloud_collector.sh --schedule
```

Your `data/` and `config/` directories are mounted into the container automatically. Cloud credentials are passed in read-only from `~/.aws`, `~/.azure`, and `~/.config/gcloud`.

---

## Running Without Docker

If you prefer to run the Python scripts directly, set up the environment first:

```bash
pip install anthropic jmespath
export ANTHROPIC_API_KEY=your_key_here

# For live mode and snapshot refresh, configure the cloud CLIs:
aws configure     # AWS
az login          # Azure
gcloud auth login # GCP
```

Then run:

```bash
python3 askloud.py               # interactive snapshot mode
python3 askloud.py --live        # interactive live mode
python3 askloud.py "list stopped instances in production"
python3 askloud_collector.py --schedule
```

---

## Modes

### Snapshot mode

Queries run entirely against local JSON files — no cloud credentials needed, no network calls. The prompt shows the age of your data:

```
[snapshot: 42min old] Ask > list running ec2 instances in dev
```

When the data for a specific account isn't in the snapshot, Askloud tells you which accounts *are* available and suggests switching to live mode.

### Live mode

Your question is translated into CLI commands by a single LLM call. The engine runs those commands locally and renders the output as a table. The CLI commands are printed before the table so you can copy-paste and tweak them:

```
[live] Ask > list ebs volumes in dev

Command(s) used:
  aws ec2 describe-volumes --profile Dev-Data-Science --region us-east-1 --output json
  aws ec2 describe-volumes --profile DevOps --region us-east-1 --output json

Profile           Region     Volume ID              Size (GB)  Type  State
Dev-Data-Science  us-east-1  vol-0a6ba94854e08269c  20         gp3   in-use
DevOps            us-east-1  vol-00f4bebb4b0341d59  20         gp3   in-use
```

When results span multiple accounts or regions, those parameters are automatically added as columns. If a command fails, the error is fed back to the LLM (up to 2 retries) so it can try alternative profiles — without sending any cloud data to the API.

---

## Usage

### Direct search (no LLM)

Single-token input scans all records in memory — no API call, no cost:

```
[snapshot: 5min old] Ask > my-web-server-01
[snapshot: 5min old] Ask > i-0abc123def456789a
[snapshot: 5min old] Ask > 10.0.1.42
```

A **Matched** column shows exactly which field triggered each hit.

### Natural language queries

```
[snapshot: 5min old] Ask > list all running instances in the production account
[snapshot: 5min old] Ask > show instances owned by the platform team
[snapshot: 5min old] Ask > vpc and subnet details for i-0abc123def456789a
[snapshot: 5min old] Ask > which instances are tagged Environment=production
```

### Shell commands and pipes

```
[snapshot: 5min old] Ask > !date
[snapshot: 5min old] Ask > !ls data/aws/accounts/
[snapshot: 5min old] Ask > list ebs in aws prod | wc -l
[live] Ask > list all vms | sort
```

### Follow-up queries (snapshot mode)

The last 10 turns are retained:
```
[snapshot: 5min old] Ask > list instances owned by the ops team
[snapshot: 5min old] Ask > which of those are stopped
[snapshot: 5min old] Ask > show the vpc for the first result
```

### Switching modes

```
/live       switch to live mode
/snapshot   switch back to snapshot mode
```

---

## Data Collector

Keep your snapshot fresh with the built-in collector:

```bash
# Run all overdue collections from the schedule
python3 askloud_collector.py --schedule

# Preview what would be collected without running anything
python3 askloud_collector.py --schedule --dry-run

# Natural language (interactive or one-shot)
python3 askloud_collector.py "get ec2 instances for production us-east-1"
```

Define what to collect and how often in `config/collection_schedule.json`:

```json
{
  "resources": [
    {
      "name":           "EC2 — Production / us-east-1",
      "provider":       "aws",
      "args":           ["ec2", "describe-instances", "--region", "us-east-1"],
      "file_path":      "data/aws/accounts/Production/us-east-1/ec2.json",
      "interval_hours": 1
    }
  ]
}
```

AWS `--profile` is auto-injected from the account folder name. Add a cron entry to run `--schedule` hourly.

---

## Data Layout

```
data/
  aws/
    accounts/
      <AccountName>/
        <region>/
          ec2.json      # aws ec2 describe-instances --output json
          vpc.json      # aws ec2 describe-vpcs --output json
          ebs.json      # aws ec2 describe-volumes --output json
  gcp/
    vm.json
  azure/
    vm.json
```

`Account`, `Region`, and `Provider` are injected onto every record from the directory path at load time.

---

## Config Files

Each resource type has a `.conf` file that controls which columns are displayed:

```
config/
  aws/ec2.conf   vpc.conf   subnet.conf   ebs.conf
  gcp/gce.conf
  azure/vm.conf
```

**Example `config/aws/ec2.conf`:**
```
Account
Region
Name
InstanceId
InstanceType
InstanceState
PrivateIP
Zone
Owner
Environment
```

Field names are resolved automatically — aliases, tag keys, nested paths, and recursive leaf search are all handled. Add or remove lines to change what appears in results — no code changes needed.

---

## Cost & Savings

Token usage is shown after every LLM call:
```
[tokens: in=2,700 out=388 cache_read=1,850 | call=$0.0021 | session total=$0.0021]
```

At exit, a session summary breaks down actual cost and estimated savings from prompt caching, direct search, and local query execution.

---

## Privacy

| Mode | What the LLM receives | Cloud data sent to API |
|---|---|---|
| Snapshot — direct search | nothing (no LLM call) | no |
| Snapshot — NL query / refresh | question + field/tag-key schema | no |
| Live | question only | no — CLI output stays on your machine |

---

## Supported Resource Types

| Type | Provider | Unique ID |
|---|---|---|
| `ec2` | AWS | `InstanceId` |
| `vpc` | AWS | `VpcId` |
| `subnet` | AWS | `SubnetId` |
| `ebs` | AWS | `VolumeId` |
| `gce` | GCP | `id` |
| `vm` | Azure | `id` |

Additional types are supported automatically — add a JSON file and a matching `.conf` file.
