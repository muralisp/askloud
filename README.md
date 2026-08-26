# Askloud

**Ask your cloud anything. Change it too.**

A conversational cloud operations tool for querying and acting on multi-cloud infrastructure across AWS, GCP, and Azure — no query language required.

Ask in plain English. Get a formatted table. Your inventory data never leaves your machine.

---

## Features

- **Three modes** — *inventory* queries DynamoDB or local JSON instantly (no CLI calls); *live* translates your question to cloud CLI commands and runs them in real time; *agentic Terraform* reads, modifies, and applies infrastructure changes end-to-end
- **Natural language queries** — powered by Claude (Anthropic), translated into structured query plans or CLI commands executed locally
- **Direct search** — single-token input (name, ID, IP) bypasses the LLM entirely; zero token cost
- **Multi-cloud** — unified interface across AWS, GCP, and Azure
- **Privacy by design** — in all modes the LLM receives only your question; actual inventory data and CLI output stay on your machine
- **Event-driven inventory** — tfstate changes in S3 automatically flow through EventBridge → Lambda → SQS → DynamoDB; EC2 state changes (start/stop/terminate) update inventory in real time
- **Agentic Terraform changes** — set/remove tags, create resources from HCL templates, or destroy resources via a guided plan-and-confirm flow; DynamoDB updates automatically after apply
- **Shell integration** — prefix `!` to run any shell command; append `| cmd` to pipe query output through it
- **Automated collection** — schedule-driven data collector keeps your snapshot fresh
- **Web GUI** — Django + Plotly chat interface at `localhost:8000`
- **Kubernetes-ready** — production deployments on AWS EKS, Azure AKS, and GCP GKE via a single deploy script per cloud
- **GitOps CI/CD** — GitHub Actions builds and pushes images; ArgoCD auto-syncs the Helm release

---
## Architecture

<img width="2814" height="1536" alt="Gemini_Generated_Image_ep6u98ep6u98ep6u" src="https://github.com/user-attachments/assets/369ac20d-f924-4979-9546-3140d1793231" />

---

## Why Askloud?

### 🗂️ Multi-account inventory at your fingertips

Managing cloud infrastructure across dozens of accounts and profiles means constantly switching CLI
contexts, running repetitive commands, and piecing together results manually. Askloud gives you a
single interface over all your AWS, GCP, and Azure inventory — ask once, get everything.

### 🌐 Built for multi-cloud environments

Modern infrastructure rarely lives in a single cloud. Teams running workloads across AWS, GCP, and
Azure face a fragmented visibility problem — each provider has its own CLI, its own data model, and
its own query syntax. Askloud normalises this into a single conversational interface. Ask about a
resource without knowing or caring which cloud it lives in, and get a unified result that spans all
three providers.

### 🗣️ Accessible to everyone on the team

Not everyone who needs cloud visibility knows JMESPath, `jq`, or CLI syntax. With Askloud, any
stakeholder — engineer, ops lead, product manager, or executive — can query infrastructure in plain
English and get a clean, formatted result. No training required.

### ⚙️ Columns without code changes

Adding or removing a field from query results is a one-line edit in a `.conf` file. No code changes,
no redeployment, no pull requests. Field names are resolved automatically from nested paths, tag keys,
and aliases — so the output adapts to your needs, not the other way around.

### 🔒 LLM-powered without exposing your data

Askloud is designed for environments where inventory data cannot leave the organisation. In both
snapshot and live modes, **only your question reaches the LLM** — never the actual resource data.
Cloud API responses and CLI output stay entirely on your machine.

### 💰 Cost-efficient LLM usage by design

Every design decision in Askloud reduces token spend:

| Optimisation | How it works |
|---|---|
| Direct search | Single-token queries bypass the LLM entirely — zero API cost |
| Prompt caching | System context is reused across turns via Anthropic's prompt cache |
| Minimal input | Only your question is sent — inventory data never reaches the API |
| No RAG | No vector store, no retrieval pipeline, no embedding overhead |
| No chat history | Context window stays flat; costs don't grow with session length |

The session summary shows exactly what you spent and what you saved.

---

## Quick Start (Docker — recommended)

Docker is the easiest way to get started. No Python setup, no CLI installations — everything is bundled in the image.

**Prerequisites:** Docker installed, an [Anthropic API key](https://console.anthropic.com/), and cloud credentials configured on your host (`aws configure`, `az login`, `gcloud auth login`).

```bash
# 1. Set your API key
export ANTHROPIC_API_KEY=your_key_here

# 2. Run the CLI
./run_askloud.sh               # interactive snapshot mode
./run_askloud.sh --live        # interactive live mode
./run_askloud.sh "list stopped instances in production"
./run_askloud_collector.sh --schedule

# 3. Or run the web GUI
docker-compose up gui
# open http://localhost:8000
```

Your `data/` and `config/` directories are mounted into the container automatically. Cloud credentials are passed in read-only from `~/.aws`, `~/.azure`, and `~/.config/gcloud`.

---

## Running Without Docker

```bash
pip install anthropic jmespath django whitenoise gunicorn
export ANTHROPIC_API_KEY=your_key_here

# For live mode and snapshot refresh, configure the cloud CLIs:
aws configure     # AWS
az login          # Azure
gcloud auth login # GCP
```

```bash
python3 askloud.py               # interactive snapshot mode
python3 askloud.py --live        # interactive live mode
python3 askloud.py "list stopped instances in production"
python3 askloud_collector.py --schedule

# Web GUI
cd askloud_gui && python manage.py runserver
# open http://localhost:8000
```

---

## Modes

### Snapshot mode

Queries run entirely against local JSON files — no cloud credentials needed, no network calls. The prompt shows the age of your data:

```
[snapshot: 42min old] Ask > list running ec2 instances in prod (Note: This is dummy data)
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
[snapshot: 5min old] Ask > web-server-01
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
[snapshot: 5min old] Ask > !ls data/aws/
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
      "file_path":      "data/aws/Production/us-east-1/ec2.json",
      "interval_hours": 1
    }
  ]
}
```

AWS `--profile` is auto-injected from the account folder name. Add a cron entry to run `--schedule` hourly, or use the Kubernetes CronJob (see below).

---

## Kubernetes Deployment

Askloud ships with deploy scripts and Terraform for production deployments on all three major clouds.

### One-command deploy

```bash
# AWS EKS
export ANTHROPIC_API_KEY=...
./deploy-eks.sh dev          # or prod

# Azure AKS
./deploy-aks.sh dev

# GCP GKE
./deploy-gke.sh dev
```

Each script:
1. Reads cluster and registry URLs from **Terraform outputs**
2. Builds and pushes both Docker images (`askloud-gui`, `askloud-engine`) to the cloud registry
3. Applies Kubernetes manifests (namespace, StorageClass, PVC, Ingress, Secrets)
4. Deploys the GUI `Deployment` and collector `CronJob`
5. Waits for rollout, then seeds local `data/` into the PVC

Optional flags:
```bash
IMAGE_TAG=v1.2.3 ./deploy-eks.sh dev   # pin a specific tag
TF_APPLY=1 ./deploy-eks.sh dev         # also run terraform apply first
```

### Storage

| Cloud | StorageClass | Provisioner |
|---|---|---|
| AWS EKS | `ebs-io2` | `ebs.csi.aws.com` (io2, 3000 IOPS) |
| Azure AKS | `azure-disk-premium` | `disk.csi.azure.com` (Premium_LRS) |
| GCP GKE | `gce-pd-ssd` | `pd.csi.storage.gke.io` (pd-ssd) |

All use `ReadWriteOnce` + `WaitForFirstConsumer`. The collector CronJob has `podAffinity` to schedule on the same node as the GUI pod so both can mount the same volume.

### Access

After deployment, the GUI and ArgoCD are both reachable through a single Nginx LoadBalancer:

```
http://<LB-hostname-or-IP>/         → Askloud GUI
http://<LB-hostname-or-IP>/argocd   → ArgoCD UI
```

---

## Event-Driven Inventory Pipeline

Askloud's inventory stays current through a fully serverless, event-driven pipeline — no scheduled polling, no manual syncs.

```
Terraform apply
  → tfstate written to S3
    → EventBridge (S3 object created)
      → Diff Lambda        — diffs new tfstate vs. DynamoDB; emits UPSERT/DELETE to SQS
        → Router Lambda    — consumes SQS batch; writes/soft-deletes DynamoDB records
          → DynamoDB       — single source of truth for all inventory queries

EC2 state change (start / stop / terminate)
  → EventBridge (EC2 Instance State-change Notification)
    → EC2 Events Lambda    — emits DELETE to SQS for terminated instances
      → Router Lambda      → DynamoDB
```

### How each component works

**Diff Lambda** (`terraform/diff_lambda.py`) — triggered by every `*.tfstate` write to a workload S3 bucket. Reads the new state, extracts all managed resources, then scans DynamoDB for existing records belonging to that workspace. Resources present in the new state become `UPSERT` messages; resources absent from it become `DELETE` messages. Using DynamoDB as the diff baseline (not S3 versioning) means the pipeline self-heals even if an event is missed.

**Router Lambda** (`terraform/router_lambda.py`) — processes SQS batches with per-message failure isolation (`batchItemFailures`). Upserts are fingerprinted (SHA-256 of normalized attributes) so unchanged resources are a cheap no-op. Deletes are soft (a `deleted=true` flag + 7-day TTL) so records are recoverable before DynamoDB purges them.

**EC2 Events Lambda** (`terraform/ec2_events_lambda.py`) — listens for `shutting-down` and `terminated` state-change events. Publishes a `DELETE` message so the inventory reflects instance termination immediately, independent of the next tfstate write.

**Reconcile script** (`ops/reconcile_inventory.py`) — a manual safety net. Reads every tfstate listed in `config/terraform_workspaces.json`, compares against DynamoDB, and soft-deletes any record with no matching live resource. Run with `--dry-run` first.

```bash
python3 ops/reconcile_inventory.py --dry-run   # preview stale records
python3 ops/reconcile_inventory.py             # soft-delete them
```

**Manual bootstrap** (`terraform/askloud_ingest.py`) — seeds DynamoDB directly from S3 tfstate files without going through the Lambda pipeline. Use this for first-time setup or disaster recovery.

```bash
python3 terraform/askloud_ingest.py --bucket askloud-tfstate --prefix dev/ --dry-run
python3 terraform/askloud_ingest.py --bucket askloud-tfstate --prefix dev/
```

### DynamoDB record layout

| Key | Format | Example |
|---|---|---|
| `PK` | `aws#ACCOUNT_ID#RESOURCE_TYPE` | `aws#099878477985#aws_instance` |
| `SK` | `REGION#RESOURCE_ID` | `ap-south-1#i-0abc123def` |
| `normalized` | Terraform attribute dict | `{instance_type: "t3.medium", ...}` |
| `deleted` | bool (soft-delete flag) | `false` |
| `fingerprint` | SHA-256 of normalized attrs | unchanged records → no write |
| `tfstate_key` | S3 key of source tfstate | used for workspace-scoped diff |

---

## Agentic Terraform Changes

Beyond querying inventory, Askloud can read, modify, and apply infrastructure changes through a guided, LLM-assisted flow — all from the same conversational interface.

### Supported operations

| Operation | What it does |
|---|---|
| `set_tag` | Adds or updates a tag on an existing resource block in-place |
| `remove_tag` | Removes a tag key from an existing resource block |
| `create_resource` | Elicits parameters interactively, renders an HCL template, appends to `main.tf` |
| `delete_resource` | Runs `terraform destroy -target=<addr>` against the resolved resource |

### Flow

1. **Resolve workspace** — looks up `config/terraform_workspaces.json` to find the Terraform path, S3 tfstate location, and AWS profile for the target resource
2. **Read tfstate from S3** — finds the exact Terraform resource address (`module.x.aws_instance.y`) matching the inventory record
3. **Edit or create** — for modify operations, patches the `.tf` file in-place and shows a unified diff for confirmation; for create, elicits missing parameters and renders an HCL template from `askloud/tf_templates.py`
4. **Plan** — runs `terraform plan -target=<addr>` and waits for user confirmation before proceeding
5. **Apply** — runs `terraform apply -auto-approve -target=<addr>`
6. **Auto-sync** — the Diff Lambda picks up the new tfstate from S3 and updates DynamoDB automatically within seconds

### Example

```
[inventory] Ask > add tag CostCenter=platform to i-0abc123def456789

  Workspace: dev / ec2 / test-inventory
  Resource:  aws_instance.web_server

  --- main.tf (before)
  +++ main.tf (after)
  @@ -12,6 +12,7 @@
     tags = {
       Name        = "web-server"
       Environment = "dev"
  +    CostCenter  = "platform"
     }

  Apply this change? [y/N] y

  Running: terraform plan -target=aws_instance.web_server
  Running: terraform apply -auto-approve -target=aws_instance.web_server

  ✓ Applied. DynamoDB will update automatically via the ingestion pipeline.
```

### Adding a new resource type

To enable agentic changes for a new resource:
1. Add a `.conf` file under `config/aws/` with display column names
2. Add entries to `FIELD_ALIASES` and `DEDUP_FIELDS` in `askloud/settings.py`
3. Add the Terraform ↔ engine type mapping in `_ENGINE_TO_TF` (`askloud/terraform_change.py`) and `_RESOURCE_TYPE_MAP` (`askloud/dynamo.py`)
4. Optionally add an HCL template function to `askloud/tf_templates.py` to enable `create_resource`

---

## CI/CD

Every push to `main` triggers the GitHub Actions workflow (`.github/workflows/deploy.yml`):

1. **OIDC auth** — exchanges a GitHub token for short-lived AWS credentials (no stored secrets)
2. **Build & push** — builds both Docker images tagged with the short git SHA and pushes to ECR
3. **Update values** — uses `yq` to write the new image tag into `helm/askloud-gui/values.yaml` and commits back with `[skip ci]`
4. **ArgoCD sync** — detects the values.yaml change and rolls out the new image automatically

ArgoCD is configured with `server.rootpath: /argocd` and `server.insecure: true` so it works behind the Nginx path-prefix ingress without a dedicated LoadBalancer.

---

## Terraform

Multi-cloud modular structure under `terraform/`:

```
terraform/
  _modules/
    aws/     vpc/  eks/  ebs-csi/  ecr/  github-oidc/     ← implemented
    azure/   network/  aks/  acr/  github-oidc/            ← scaffold
    gcp/     vpc/  gke/  artifact-registry/  github-oidc/  ← scaffold
  _policies/
    required_tags.rego          # OPA/Conftest — enforces tags on all clouds
    aws/  .tflint.hcl  .checkov.yaml
    azure/ .tflint.hcl  .checkov.yaml
    gcp/   .tflint.hcl  .checkov.yaml
  dev/
    aws/    ← active (ap-south-1, t3.medium × 2)
    azure/  ← scaffold
    gcp/    ← scaffold
  prod/
    aws/    ← active (ap-south-1, t3.large × 3, multi-AZ NAT)
    azure/  ← scaffold
    gcp/    ← scaffold
```

Tagging policy is enforced shift-left: `aws_default_tags` / `azurerm default_tags` / `google default_labels` inject the four required labels (`Project`, `Environment`, `ManagedBy`, `Owner`) at the provider level. The OPA policy is the CI gate that confirms no resource slips through.

---

## Data Layout

```
data/
  aws/
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
