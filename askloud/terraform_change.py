"""
Agentic Terraform change execution.

Supported operations:
  set_tag / remove_tag  — edit an existing resource block in-place
  create_resource       — interactively gather params, render an HCL template,
                          append to main.tf, then plan → apply
  delete_resource       — terraform destroy -target=<addr>

Flow:
  1. Resolve workspace from config/terraform_workspaces.json
  2. (modify/delete) Read tfstate from S3 → find resource address
     (modify) Edit .tf file
     (create) Elicit missing params from user, render HCL template
  3. (modify) Show diff → user confirms write
  4. terraform plan [-destroy] -target=<addr> → user confirms
  5. terraform apply/destroy -auto-approve -target=<addr>
  6. Diff Lambda picks up new tfstate → DynamoDB updated automatically
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Optional

VIZ_BASE_DIR = "/tmp/askloud_rover"

# Engine resource type → Terraform resource type
_ENGINE_TO_TF = {
    "ec2":              "aws_instance",
    "vpc":              "aws_vpc",
    "subnet":           "aws_subnet",
    "igw":              "aws_internet_gateway",
    "nat_gateway":      "aws_nat_gateway",
    "eip":              "aws_eip",
    "route_table":      "aws_route_table",
    "security_group":   "aws_security_group",
    "iam_role":         "aws_iam_role",
    "ecr_repository":   "aws_ecr_repository",
    "lambda_function":  "aws_lambda_function",
    "sqs_queue":        "aws_sqs_queue",
    "dynamodb_table":   "aws_dynamodb_table",
    "event_bus":        "aws_cloudwatch_event_bus",
    "eventbridge_rule": "aws_cloudwatch_event_rule",
    "log_group":        "aws_cloudwatch_log_group",
}

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─────────────────────────────────────────────────────────────────────────────
# Registry helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_registry() -> list[dict]:
    path = os.path.join(_REPO_ROOT, "config", "terraform_workspaces.json")
    with open(path) as f:
        return json.load(f)["workspaces"]


def _find_workspace(registry: list[dict], tf_type: str, account: str) -> Optional[dict]:
    for ws in registry:
        if ws["account"] == account and tf_type in ws.get("terraform_types", []):
            return ws
    return None


# ─────────────────────────────────────────────────────────────────────────────
# tfstate lookup
# ─────────────────────────────────────────────────────────────────────────────

def _read_tfstate(bucket: str, key: str, region: str, profile: Optional[str]) -> dict:
    import boto3
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    body = session.client("s3", region_name=region).get_object(
        Bucket=bucket, Key=key
    )["Body"].read()
    return json.loads(body)


def _find_resource_address(state: dict, tf_type: str, resource_id: str) -> Optional[str]:
    """Return the Terraform address (e.g. 'aws_instance.this') for the given AWS resource ID."""
    for res in state.get("resources", []):
        if res.get("type") != tf_type:
            continue
        for inst in res.get("instances", []):
            if inst.get("attributes", {}).get("id") == resource_id:
                module = res.get("module", "")
                name   = res.get("name", "")
                addr   = f"{tf_type}.{name}"
                if module:
                    addr = f"{module}.{addr}"
                return addr
    return None


# ─────────────────────────────────────────────────────────────────────────────
# HCL file editing
# ─────────────────────────────────────────────────────────────────────────────

def _find_tf_file(workspace_path: str, tf_type: str, resource_name: str) -> Optional[str]:
    """Find the *.tf file that contains: resource "<tf_type>" "<resource_name>" {"""
    pattern = re.compile(
        rf'resource\s+"{re.escape(tf_type)}"\s+"{re.escape(resource_name)}"'
    )
    for tf_file in sorted(Path(workspace_path).glob("*.tf")):
        if pattern.search(tf_file.read_text()):
            return str(tf_file)
    return None


def _resource_block_bounds(content: str, tf_type: str, resource_name: str) -> Optional[tuple[int, int]]:
    """Return (start, end) indices of the resource block (inclusive of braces)."""
    pattern = re.compile(
        rf'resource\s+"{re.escape(tf_type)}"\s+"{re.escape(resource_name)}"\s*\{{'
    )
    m = pattern.search(content)
    if not m:
        return None
    depth = 0
    for i, ch in enumerate(content[m.start():], m.start()):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return m.start(), i
    return None


def _apply_set_tag(content: str, tf_type: str, resource_name: str,
                   tag_key: str, tag_value: str) -> Optional[str]:
    bounds = _resource_block_bounds(content, tf_type, resource_name)
    if bounds is None:
        return None
    start, end = bounds
    block = content[start:end + 1]

    # Find the tags = { ... } block inside the resource block
    tags_re = re.compile(r'(\btags\s*=\s*\{)([^}]*)(\})', re.DOTALL)
    tm = tags_re.search(block)

    if tm:
        body = tm.group(2)
        key_re = re.compile(rf'(\b{re.escape(tag_key)}\s*=\s*)([^\n]+)')
        if key_re.search(body):
            new_body = key_re.sub(rf'\g<1>"{tag_value}"', body)
        else:
            # Detect indentation from existing entries, default to 4 spaces
            indent_m = re.search(r'\n(\s+)\S', body)
            indent = indent_m.group(1) if indent_m else "    "
            new_body = body.rstrip("\n") + f'\n{indent}{tag_key} = "{tag_value}"\n  '
        new_block = block[:tm.start(1)] + tm.group(1) + new_body + tm.group(3) + block[tm.end():]
    else:
        # No tags block — add one before the closing brace
        new_tags = f'\n\n  tags = {{\n    {tag_key} = "{tag_value}"\n  }}\n'
        new_block = block[:-1] + new_tags + "}"

    return content[:start] + new_block + content[end + 1:]


def _apply_remove_tag(content: str, tf_type: str, resource_name: str,
                      tag_key: str) -> Optional[str]:
    bounds = _resource_block_bounds(content, tf_type, resource_name)
    if bounds is None:
        return None
    start, end = bounds
    block = content[start:end + 1]

    tags_re = re.compile(r'(\btags\s*=\s*\{)([^}]*)(\})', re.DOTALL)
    tm = tags_re.search(block)
    if not tm:
        return content  # no tags block, nothing to remove

    body = tm.group(2)
    key_re = re.compile(rf'\n\s*{re.escape(tag_key)}\s*=[^\n]*')
    new_body = key_re.sub("", body)
    new_block = block[:tm.start(2)] + new_body + block[tm.end(2):]
    return content[:start] + new_block + content[end + 1:]


# ─────────────────────────────────────────────────────────────────────────────
# Resource creation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resource_name_exists(workspace_path: str, tf_type: str, resource_name: str) -> bool:
    """Return True if resource "<tf_type>" "<resource_name>" already exists in the workspace."""
    pattern = re.compile(
        rf'resource\s+"{re.escape(tf_type)}"\s+"{re.escape(resource_name)}"'
    )
    for tf_file in Path(workspace_path).glob("*.tf"):
        if pattern.search(tf_file.read_text()):
            return True
    return False


def _filter_by_account(records: list, account: str) -> list:
    account_lower = account.lower()
    return [r for r in records if account_lower in r.get("Account", "").lower()]


def _select_from_inventory(param_spec: dict, records: list) -> Optional[str]:
    """Show a numbered pick-list and return the chosen field value, or None to abort."""
    field    = param_spec["inventory_field"]
    label_fn = param_spec.get("inventory_label", lambda r: r.get(field, ""))

    print(f"\n  Available {param_spec['prompt'].lower()}:")
    for i, r in enumerate(records, 1):
        try:
            label = label_fn(r)
        except Exception:
            label = r.get(field, "?")
        print(f"    [{i}] {label}")
    print("    [m] Enter manually")

    try:
        raw = input("  Choice [1]: ").strip()
    except EOFError:
        return None

    if not raw:
        raw = "1"

    if raw.lower() == "m":
        try:
            return input(f"  {param_spec['prompt']}: ").strip() or None
        except EOFError:
            return None

    try:
        idx = int(raw) - 1
        if 0 <= idx < len(records):
            return records[idx].get(field, "")
        print("\033[31m  Invalid choice.\033[0m")
        return None
    except ValueError:
        print("\033[31m  Invalid choice.\033[0m")
        return None


def _elicit_params(template_def: dict, step_params: dict,
                   account: str, loader) -> Optional[dict]:
    """
    Prompt the user for each missing parameter in template_def["params"].
    Returns a complete params dict, or None if the user aborts.
    In non-interactive contexts (GUI/pipes) fills defaults and lists missing required params.
    """
    params = {k: v for k, v in step_params.items() if v}  # start with LLM-provided values

    if not sys.stdin.isatty():
        # Non-interactive: fill optional defaults, report any still-missing required params.
        for p in template_def["params"]:
            if not params.get(p["name"]) and not p["required"] and p.get("default") is not None:
                params[p["name"]] = p["default"]
        missing = [p for p in template_def["params"] if p["required"] and not params.get(p["name"])]
        if missing:
            print("To complete this request, include the following details in your message:")
            for m in missing:
                print(f"  • {m['prompt']}")
            return None
        return params

    for p in template_def["params"]:
        pname = p["name"]

        if params.get(pname):  # already filled
            continue

        # Inventory-backed pick-list
        inv_resource = p.get("inventory_resource")
        if inv_resource and loader is not None:
            records = _filter_by_account(
                loader.data.get(inv_resource, []), account
            )
            if records:
                val = _select_from_inventory(p, records)
                if val is None:
                    print("\033[33mAborted.\033[0m")
                    return None
                params[pname] = val
                continue

        # Plain interactive prompt
        default = p.get("default")
        if not p["required"] and default is not None:
            prompt_str = f"  {p['prompt']} [{default}]: "
        else:
            prompt_str = f"  {p['prompt']}: "

        try:
            val = input(prompt_str).strip()
        except EOFError:
            return None

        if not val:
            if p["required"]:
                print(f"\033[31m  '{pname}' is required.\033[0m")
                return None
            val = default or ""

        params[pname] = val

    return params


def _create_resource(step: dict, bindings: dict, loader) -> bool:
    """Handle operation=create_resource: elicit params, render HCL, plan, apply."""
    from .tf_templates import TEMPLATES, _to_resource_name

    def _resolve(v):
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            return bindings.get(v[1:-1], v)
        return v

    engine_type = _resolve(step.get("resource", ""))
    account     = _resolve(step.get("account", ""))
    step_params = {k: _resolve(v) for k, v in (step.get("params") or {}).items()}

    tmpl_def = TEMPLATES.get(engine_type)
    if not tmpl_def:
        print(f"\033[31mNo creation template for resource type '{engine_type}'.\033[0m")
        print(f"\033[33mSupported types: {', '.join(TEMPLATES)}\033[0m")
        return False

    tf_type = _ENGINE_TO_TF.get(engine_type)
    if not tf_type:
        print(f"\033[31mNo Terraform type mapping for '{engine_type}'.\033[0m")
        return False

    try:
        registry = _load_registry()
    except FileNotFoundError:
        print("\033[31mWorkspace registry missing: config/terraform_workspaces.json\033[0m")
        return False

    # Auto-detect account when unresolved: use the single workspace for this type
    if not account or account.startswith("{"):
        candidates = [ws for ws in registry if tf_type in ws.get("terraform_types", [])]
        if len(candidates) == 1:
            account = candidates[0]["account"]

    # ── Non-interactive (GUI) path ────────────────────────────────────────────
    # Always show the form so the user can review / edit pre-filled values
    # (e.g. from a clone bind step).  Skip only when the form has already been
    # submitted (from_form=True set by engine_wrapper.execute_provision).
    if not sys.stdin.isatty() and not step.get("from_form"):
        prefilled = {k: v for k, v in step_params.items() if v}
        for p in tmpl_def["params"]:
            if not prefilled.get(p["name"]) and not p["required"] and p.get("default") is not None:
                prefilled[p["name"]] = p["default"]

        form_params = [
            {
                "name":     p["name"],
                "prompt":   p["prompt"],
                "required": p["required"],
                "default":  p.get("default", ""),
                "value":    prefilled.get(p["name"], ""),
            }
            for p in tmpl_def["params"]
        ]
        ws_try   = _find_workspace(registry, tf_type, account)
        ws_label = ws_try["label"] if ws_try else ""
        import json as _json
        print(f"__FORM_SPEC__:{_json.dumps({'resource_type': engine_type, 'resource_label': tmpl_def['label'], 'account': account, 'workspace': ws_label, 'params': form_params})}")
        return False
    # ─────────────────────────────────────────────────────────────────────────

    ws = _find_workspace(registry, tf_type, account)
    if not ws:
        # Account name was wrong/unknown — try to resolve by resource type alone
        candidates = [w for w in registry if tf_type in w.get("terraform_types", []) and not w.get("uses_modules")]
        if len(candidates) == 1:
            ws = candidates[0]
            account = ws["account"]
        elif not candidates:
            print(f"\033[31mNo workspace registered for {engine_type}.\033[0m")
            print("\033[33mAdd an entry to config/terraform_workspaces.json to enable this.\033[0m")
            return False
        else:
            accts = ", ".join(sorted(set(w["account"] for w in candidates)))
            print(f"\033[31mMultiple workspaces found for {engine_type}. Specify account: {accts}\033[0m")
            return False

    ws_path = os.path.join(_REPO_ROOT, ws["path"])
    profile = ws.get("profile")

    if ws.get("uses_modules"):
        print(f"\033[31mWorkspace '{ws['label']}' uses Terraform modules — direct creation not supported yet.\033[0m")
        return False

    print(f"\n\033[33mCreating {tmpl_def['label']} in workspace: {ws['label']}\033[0m")
    print("Fill in the parameters below (press Enter to accept defaults):\n")

    # Elicit missing parameters interactively
    params = _elicit_params(tmpl_def, step_params, account, loader)
    if params is None:
        return False

    resource_name = _to_resource_name(params["name"])

    # Guard against duplicate resource names
    if _resource_name_exists(ws_path, tf_type, resource_name):
        print(f"\033[31mResource \"{tf_type}\" \"{resource_name}\" already exists in {ws_path}.\033[0m")
        print("\033[33mChoose a different name or edit the existing resource.\033[0m")
        return False

    # Render HCL
    try:
        new_hcl = tmpl_def["render"](params)
    except Exception as exc:
        print(f"\033[31mTemplate rendering failed: {exc}\033[0m")
        return False

    target_file = os.path.join(ws_path, "main.tf")
    original    = Path(target_file).read_text() if os.path.exists(target_file) else ""
    modified    = original + new_hcl

    # Show the new block
    print(f"\n\033[33mNew resource to be added ({os.path.relpath(target_file, _REPO_ROOT)}):\033[0m\n")
    for line in new_hcl.splitlines():
        print(f"\033[32m+ {line}\033[0m")
    print()

    if not _confirm("Write this resource? [y/N] "):
        print("\033[33mAborted.\033[0m")
        return False

    Path(target_file).write_text(modified)

    tf_addr = f"{tf_type}.{resource_name}"

    # terraform init (always reconfigure to handle backend drift)
    if not _ensure_initialized(ws_path, profile):
        print("\033[31mterraform init failed.\033[0m")
        Path(target_file).write_text(original)
        return False

    # terraform plan
    print(f"\n\033[90mRunning: terraform plan -target={tf_addr}\033[0m\n")
    rc = _run_terraform(["plan", f"-target={tf_addr}"], ws_path, profile)
    if rc != 0:
        print("\033[31mterraform plan failed. Reverting file.\033[0m")
        Path(target_file).write_text(original)
        return False

    if not _confirm("\nApply? [y/N] "):
        print("\033[33m.tf file updated but not applied. Run 'terraform apply' manually when ready.\033[0m")
        return True

    print(f"\n\033[90mRunning: terraform apply -auto-approve -target={tf_addr}\033[0m\n")
    rc = _run_terraform(["apply", "-auto-approve", f"-target={tf_addr}"], ws_path, profile)
    if rc != 0:
        print("\033[31mterraform apply failed.\033[0m")
        return False

    print(f"\n\033[32mDone. {tmpl_def['label']} '{params['name']}' created.\033[0m")
    print("\033[90mThe pipeline will ingest the new resource into DynamoDB automatically.\033[0m\n")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Terraform subprocess helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_terraform(args: list[str], cwd: str, profile: Optional[str]) -> int:
    env = os.environ.copy()
    if profile:
        env["AWS_PROFILE"] = profile
    proc = subprocess.Popen(
        ["terraform"] + args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in proc.stdout:
        print(line, end="", flush=True)
    proc.wait()
    return proc.returncode


def _show_diff(original: str, modified: str, label: str = ""):
    if label:
        print(f"\033[90m{label}\033[0m")
    for line in difflib.unified_diff(
        original.splitlines(), modified.splitlines(), lineterm="", n=3
    ):
        if line.startswith("+++") or line.startswith("---"):
            print(f"\033[90m{line}\033[0m")
        elif line.startswith("+"):
            print(f"\033[32m{line}\033[0m")
        elif line.startswith("-"):
            print(f"\033[31m{line}\033[0m")
        else:
            print(f"\033[90m{line}\033[0m")
    print()


def _confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return True  # user already expressed intent; auto-confirm in GUI/pipe contexts
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Plan / apply / decline  (GUI two-step flow)
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_initialized(ws_path: str, profile: Optional[str]) -> bool:
    """
    Run terraform init -reconfigure before every plan.
    -reconfigure updates the backend pointer and provider cache without
    touching remote state, so it is safe to run unconditionally and handles
    both first-time init and "backend config changed" drift.
    """
    print("Initializing Terraform workspace…")
    return _run_terraform(["init", "-reconfigure", "-no-color"], ws_path, profile) == 0


def _get_plan_data(plan_file: str, ws_path: str, profile: Optional[str]) -> Optional[dict]:
    """
    Run 'terraform show -json' on the binary plan file and return a structured
    summary suitable for rendering a diff view in the GUI.
    Returns None if the command fails or the JSON is unparseable.
    """
    _ACTION_MAP = {
        "create":        "create",
        "update":        "update",
        "delete":        "destroy",
        "delete+create": "replace",
        "create+delete": "replace",
    }

    env = os.environ.copy()
    if profile:
        env["AWS_PROFILE"] = profile

    try:
        result = subprocess.run(
            ["terraform", "show", "-json", plan_file],
            cwd=ws_path, env=env,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
    except Exception:
        return None

    # Keys to hide — they're noisy and rarely relevant at review time
    _HIDE_KEYS = frozenset({
        "id", "arn", "tags_all", "owner_id", "owner_alias",
        "timeouts", "default_cooldown", "availability_zone_id",
    })

    changes = []
    for rc in data.get("resource_changes", []):
        actions    = rc.get("change", {}).get("actions", ["no-op"])
        action_key = "+".join(actions)
        action     = _ACTION_MAP.get(action_key)
        if not action:           # no-op / read — skip
            continue

        after = rc.get("change", {}).get("after") or {}
        attrs = {
            k: v for k, v in after.items()
            if v is not None
            and not isinstance(v, (dict, list))
            and k not in _HIDE_KEYS
        }

        changes.append({
            "address": rc.get("address", ""),
            "type":    rc.get("type", ""),
            "name":    rc.get("name", ""),
            "action":  action,
            "attrs":   attrs,
        })

    summary = {
        "add":     sum(1 for c in changes if c["action"] == "create"),
        "update":  sum(1 for c in changes if c["action"] == "update"),
        "destroy": sum(1 for c in changes if c["action"] in ("destroy", "replace")),
    }

    return {"summary": summary, "changes": changes}


def plan_resource(step: dict, bindings: dict, loader) -> dict:
    """
    Write HCL, run terraform init (if needed) + plan, generate rover viz.

    Returns:
      {"token": str, "plan_data": dict|None, "error": str|None}
    """
    from .tf_templates import TEMPLATES, _to_resource_name

    def _resolve(v):
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            return bindings.get(v[1:-1], v)
        return v

    engine_type = step.get("resource", "")
    account     = step.get("account", "")
    step_params = {k: _resolve(v) for k, v in (step.get("params") or {}).items()}

    tmpl_def = TEMPLATES.get(engine_type)
    if not tmpl_def:
        return {"error": f"No creation template for resource type '{engine_type}'."}

    tf_type = _ENGINE_TO_TF.get(engine_type)
    if not tf_type:
        return {"error": f"No Terraform type mapping for '{engine_type}'."}

    try:
        registry = _load_registry()
    except FileNotFoundError:
        return {"error": "Workspace registry missing: config/terraform_workspaces.json"}

    if not account or account.startswith("{"):
        candidates = [ws for ws in registry if tf_type in ws.get("terraform_types", [])]
        if len(candidates) == 1:
            account = candidates[0]["account"]

    ws = _find_workspace(registry, tf_type, account)
    if not ws:
        # Account name was wrong/unknown — try to resolve by resource type alone
        candidates = [w for w in registry if tf_type in w.get("terraform_types", []) and not w.get("uses_modules")]
        if len(candidates) == 1:
            ws = candidates[0]
            account = ws["account"]
        elif not candidates:
            return {"error": f"No workspace registered for {engine_type}. Add an entry to config/terraform_workspaces.json."}
        else:
            accts = ", ".join(sorted(set(w["account"] for w in candidates)))
            return {"error": f"Multiple workspaces found for {engine_type}. Specify account: {accts}"}

    ws_path = os.path.join(_REPO_ROOT, ws["path"])
    profile = ws.get("profile")

    # Fill params: start with LLM-provided values then apply defaults
    params = {k: v for k, v in step_params.items() if v}
    for p in tmpl_def["params"]:
        if not params.get(p["name"]) and not p["required"] and p.get("default") is not None:
            params[p["name"]] = p["default"]

    missing = [p for p in tmpl_def["params"] if p["required"] and not params.get(p["name"])]
    if missing:
        return {"error": "Missing required fields: " + ", ".join(m["prompt"] for m in missing)}

    resource_name = _to_resource_name(params["name"])
    tf_addr = f"{tf_type}.{resource_name}"

    if _resource_name_exists(ws_path, tf_type, resource_name):
        return {"error": f'Resource "{tf_type}" "{resource_name}" already exists in {ws_path}.'}

    try:
        new_hcl = tmpl_def["render"](params)
    except Exception as exc:
        return {"error": f"Template rendering failed: {exc}"}

    target_file = os.path.join(ws_path, "main.tf")
    original    = Path(target_file).read_text() if os.path.exists(target_file) else ""
    Path(target_file).write_text(original + new_hcl)

    # Persist plan state so apply/decline can find everything later
    token     = uuid.uuid4().hex
    state_dir = os.path.join(VIZ_BASE_DIR, token)
    os.makedirs(state_dir, exist_ok=True)
    state = {
        "ws_path": ws_path, "tf_addr": tf_addr, "tf_file": target_file,
        "original": original, "profile": profile,
        "resource_name": resource_name, "label": tmpl_def["label"],
    }
    Path(os.path.join(state_dir, "state.json")).write_text(json.dumps(state))

    # terraform init (idempotent guard)
    if not _ensure_initialized(ws_path, profile):
        Path(target_file).write_text(original)
        shutil.rmtree(state_dir, ignore_errors=True)
        return {"error": "terraform init failed — check provider credentials / network."}

    # terraform plan → binary plan file
    plan_file = os.path.join(state_dir, "tfplan.out")
    print(f"\nRunning: terraform plan -target={tf_addr}\n")
    rc = _run_terraform(
        ["plan", f"-target={tf_addr}", f"-out={plan_file}", "-no-color"],
        ws_path, profile,
    )
    if rc != 0:
        Path(target_file).write_text(original)
        shutil.rmtree(state_dir, ignore_errors=True)
        return {"error": "terraform plan failed — see plan output above for details."}

    # Parse structured plan data for the GUI diff viewer
    plan_data = _get_plan_data(plan_file, ws_path, profile)

    return {"token": token, "plan_data": plan_data, "error": None}


def apply_resource(token: str) -> dict:
    """
    Apply a previously planned resource creation (identified by token).
    Cleans up plan state dir regardless of outcome.
    Returns {} on success or {"error": str} on failure.
    """
    state_dir  = os.path.join(VIZ_BASE_DIR, token)
    state_file = os.path.join(state_dir, "state.json")

    if not os.path.isfile(state_file):
        return {"error": f"Plan session not found or already consumed (token={token!r})."}

    state         = json.loads(Path(state_file).read_text())
    ws_path       = state["ws_path"]
    tf_addr       = state["tf_addr"]
    profile       = state.get("profile")
    label         = state.get("label", "Resource")
    resource_name = state.get("resource_name", "")

    print(f"\nRunning: terraform apply -auto-approve -target={tf_addr}\n")
    rc = _run_terraform(
        ["apply", "-auto-approve", f"-target={tf_addr}", "-no-color"],
        ws_path, profile,
    )

    shutil.rmtree(state_dir, ignore_errors=True)   # cleanup regardless of outcome

    if rc != 0:
        return {"error": "terraform apply failed — check apply output above."}

    print(f"\nDone. {label} '{resource_name}' created successfully.")
    print("The pipeline will ingest the new resource into DynamoDB automatically.\n")
    return {}


def decline_resource(token: str) -> dict:
    """
    Revert the .tf file written during plan and discard plan state.
    Returns {} always (errors are non-fatal).
    """
    state_dir  = os.path.join(VIZ_BASE_DIR, token)
    state_file = os.path.join(state_dir, "state.json")

    if not os.path.isfile(state_file):
        return {}

    state = json.loads(Path(state_file).read_text())
    try:
        Path(state["tf_file"]).write_text(state["original"])
    except Exception as exc:
        print(f"Warning: could not revert terraform file: {exc}")

    shutil.rmtree(state_dir, ignore_errors=True)
    print("Plan declined — terraform file reverted.")
    return {}


def _delete_resource(ws_path: str, profile: Optional[str], tf_addr: str, resource_id: str) -> bool:
    """Run terraform destroy -target=<tf_addr> after two confirmation prompts."""
    print(f"\033[31mThis will permanently destroy {resource_id} in AWS and remove it from Terraform state.\033[0m")

    if not _confirm("Confirm destruction? [y/N] "):
        print("\033[33mAborted.\033[0m")
        return False

    print(f"\n\033[90mRunning: terraform plan -destroy -target={tf_addr}\033[0m\n")
    rc = _run_terraform(["plan", "-destroy", f"-target={tf_addr}"], ws_path, profile)
    if rc != 0:
        print("\033[31mterraform plan -destroy failed.\033[0m")
        return False

    if not _confirm("\nApply destroy? [y/N] "):
        print("\033[33mAborted — nothing was destroyed.\033[0m")
        return False

    print(f"\n\033[90mRunning: terraform destroy -auto-approve -target={tf_addr}\033[0m\n")
    rc = _run_terraform(["destroy", "-auto-approve", f"-target={tf_addr}"], ws_path, profile)
    if rc != 0:
        print("\033[31mterraform destroy failed.\033[0m")
        return False

    print(f"\n\033[32mDone. {resource_id} has been destroyed.\033[0m")
    print("\033[90mThe pipeline will update DynamoDB automatically within seconds.\033[0m\n")
    return True


def execute_terraform_change(step: dict, bindings: dict, loader=None) -> bool:
    """
    Execute one terraform_change step from a query plan.

    Supported operations:
      set_tag         — add/update a tag on an existing resource
      remove_tag      — remove a tag from an existing resource
      create_resource — create a new resource from an HCL template
      delete_resource — permanently destroy a resource via terraform destroy

    step keys (set_tag / remove_tag / delete_resource):
      resource     — engine resource type (e.g. "ec2")
      resource_id  — AWS resource ID (e.g. "i-0079a6ebb2d95a73e")
      account      — friendly account name (e.g. "dev") or {binding}
      operation    — "set_tag" | "remove_tag" | "delete_resource"
      tag_key      — the tag key (set_tag / remove_tag only)
      tag_value    — the tag value (set_tag only)

    step keys (create_resource):
      resource     — engine resource type (e.g. "ec2")
      account      — friendly account name
      operation    — "create_resource"
      params       — dict of pre-filled parameter values (may be partial)
    """
    operation = step.get("operation", "")

    # Route creation separately — no resource_id lookup needed
    if operation == "create_resource":
        return _create_resource(step, bindings, loader)

    # Resolve any {binding} placeholders
    def _resolve(v):
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            return bindings.get(v[1:-1], v)
        return v

    engine_type = _resolve(step.get("resource", ""))
    resource_id = _resolve(step.get("resource_id", ""))
    account     = _resolve(step.get("account", ""))
    tag_key     = step.get("tag_key", "")
    tag_value   = step.get("tag_value", "")

    tf_type = _ENGINE_TO_TF.get(engine_type)
    if not tf_type:
        print(f"\033[31mTerraform changes are not supported for resource type '{engine_type}'.\033[0m")
        return False

    # ── 1. Workspace lookup ────────────────────────────────────────────────────
    try:
        registry = _load_registry()
    except FileNotFoundError:
        print("\033[31mWorkspace registry missing: config/terraform_workspaces.json\033[0m")
        return False

    ws = _find_workspace(registry, tf_type, account)
    if not ws:
        print(f"\033[31mNo Terraform workspace registered for {engine_type} in account '{account}'.\033[0m")
        print("\033[33mAdd an entry to config/terraform_workspaces.json to enable this.\033[0m")
        return False

    ws_path = os.path.join(_REPO_ROOT, ws["path"])
    profile = ws.get("profile")
    region  = ws.get("region")

    if ws.get("uses_modules") and operation not in ("delete_resource",):
        print(f"\033[31mWorkspace '{ws['label']}' uses Terraform modules.\033[0m")
        print("\033[33mDirect resource editing is not supported for module-based workspaces yet.\033[0m")
        return False

    # ── 2. Resolve resource address from tfstate ───────────────────────────────
    print(f"\033[90mLooking up {resource_id} in {ws['tfstate_key']}...\033[0m")
    try:
        state   = _read_tfstate(ws["tfstate_bucket"], ws["tfstate_key"], region, profile)
        tf_addr = _find_resource_address(state, tf_type, resource_id)
    except Exception as exc:
        print(f"\033[31mFailed to read tfstate from S3: {exc}\033[0m")
        return False

    if not tf_addr:
        print(f"\033[31m{resource_id} not found in tfstate. Has it been applied yet?\033[0m")
        return False

    resource_name = tf_addr.rsplit(".", 1)[-1]  # "aws_instance.this" → "this"
    print(f"\033[90mFound: {tf_addr}\033[0m")

    if operation == "delete_resource":
        return _delete_resource(ws_path, profile, tf_addr, resource_id)

    # ── 3. Find the .tf file ───────────────────────────────────────────────────
    tf_file = _find_tf_file(ws_path, tf_type, resource_name)
    if not tf_file:
        print(f"\033[31mCould not find resource \"{tf_type}\" \"{resource_name}\" in {ws_path}\033[0m")
        return False

    original = Path(tf_file).read_text()

    # ── 4. Build the modified content ──────────────────────────────────────────
    if operation == "set_tag":
        if not tag_key:
            print("\033[31mset_tag requires tag_key.\033[0m")
            return False
        modified = _apply_set_tag(original, tf_type, resource_name, tag_key, tag_value)
        summary  = f'Set tag {tag_key} = "{tag_value}" on {tf_addr}'

    elif operation == "remove_tag":
        if not tag_key:
            print("\033[31mremove_tag requires tag_key.\033[0m")
            return False
        modified = _apply_remove_tag(original, tf_type, resource_name, tag_key)
        summary  = f"Remove tag {tag_key} from {tf_addr}"

    else:
        print(f"\033[31mUnsupported operation '{operation}'. Supported: set_tag, remove_tag, delete_resource.\033[0m")
        return False

    if modified is None:
        print(f"\033[31mCould not locate resource block in {tf_file}\033[0m")
        return False

    if modified == original:
        print(f"\033[33mNo change needed — already has the requested value.\033[0m")
        return True

    # ── 5. Show diff and confirm write ─────────────────────────────────────────
    print(f"\033[33m{summary}\033[0m")
    _show_diff(original, modified, label=f"File: {os.path.relpath(tf_file, _REPO_ROOT)}")

    if not _confirm("Write this change? [y/N] "):
        print("\033[33mAborted.\033[0m")
        return False

    Path(tf_file).write_text(modified)

    # ── 6. terraform plan ─────────────────────────────────────────────────────
    print(f"\n\033[90mRunning: terraform plan -target={tf_addr}\033[0m\n")
    rc = _run_terraform(["plan", f"-target={tf_addr}"], ws_path, profile)
    if rc != 0:
        print("\033[31mterraform plan failed. Reverting file.\033[0m")
        Path(tf_file).write_text(original)
        return False

    # ── 7. Confirm apply ──────────────────────────────────────────────────────
    if not _confirm("\nApply? [y/N] "):
        print("\033[33m.tf file updated but not applied. Run 'terraform apply' manually when ready.\033[0m")
        return True

    # ── 8. terraform apply ────────────────────────────────────────────────────
    print(f"\n\033[90mRunning: terraform apply -auto-approve -target={tf_addr}\033[0m\n")
    rc = _run_terraform(["apply", "-auto-approve", f"-target={tf_addr}"], ws_path, profile)
    if rc != 0:
        print("\033[31mterraform apply failed.\033[0m")
        return False

    print(f"\n\033[32mDone. {summary}.\033[0m")
    print("\033[90mThe pipeline will update DynamoDB automatically within seconds.\033[0m\n")
    return True
