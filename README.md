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
