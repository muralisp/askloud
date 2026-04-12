"""
System prompt builder.

build_system_prompt(loader) reads the current state of a DataLoader and returns
the full system prompt string passed to the LLM on every query.
"""

from .loader import DataLoader


def build_system_prompt(loader: DataLoader) -> str:
    resource_lines = "\n".join(
        f"  {rt}  ({loader.record_counts.get(rt, 0)} records)"
        for rt in sorted(loader.data)
    )

    schema_sections = []
    for rt in sorted(loader.schemas):
        default_fields = loader.configs.get(rt, [])
        schema_fields  = loader.schemas[rt]
        other_lines    = [p for p in schema_fields if not p.startswith("Tags[")]

        # Only include meta fields that are actually populated from the directory structure
        meta        = loader.populated_meta.get(rt, set())
        meta_fields = [f for f in ("Account", "Region", "Provider") if f in meta]
        other_lines = [p for p in other_lines if p not in ("Account", "Region", "Provider")]
        if meta_fields:
            other_lines = meta_fields + other_lines

        prompt_keys = loader.prompt_tag_keys(rt)
        tags_line   = (
            f"    Tags[{{Key,Value}}]  # keys: {', '.join(prompt_keys)}"
            if prompt_keys else ""
        )
        field_list = "\n".join(f"    {p}" for p in other_lines[:49])
        if tags_line:
            field_list += "\n" + tags_line

        schema_sections.append(
            f"### {rt}\n"
            f"  Default display fields: {', '.join(default_fields) if default_fields else '(none configured)'}\n"
            f"  Fields:\n{field_list}"
        )

    schemas_str = "\n\n".join(schema_sections)

    # File index shown to the LLM so it can construct accurate refresh file_paths
    file_lines = []
    for rt in sorted(loader.file_sources):
        for src in loader.file_sources[rt]:
            file_lines.append(
                f"  {rt}: {src['file_path']}  "
                f"(account={src['account']} region={src['region']} provider={src['provider']})"
            )
    files_str = "\n".join(file_lines) if file_lines else "  (none)"

    return f"""You are a Cloud Inventory Expert. Translate natural language queries into a JSON query plan.

## Available Resources
{resource_lines}

## Loaded Data Files
{files_str}

## Field Schemas
{schemas_str}

## Response Format
Return ONLY a raw JSON object — no markdown, no explanation. Schema:
{{
  "title": "human-readable description",
  "steps": [
    {{
      "action":        "query",
      "resource":      "<resource name>",
      "filter":        "<jmespath expression on the records array, or null>",
      "icontains":     {{"field": "substring"}},
      "tag_icontains": {{"TagKey": "substring"}},
      "tag_equals":    {{"TagKey": "exact_value"}},
      "columns": [
        {{"header": "ColName", "path": "<jmespath on single record>", "default": "N/A"}}
      ],
      "bind":          {{"var_name": "<jmespath on single record from results[0]>"}},
      "show":          true,
      "count_only":    false,
      "dedupe_field":  "<field name>"
    }}
  ]
}}

For refresh/latest data requests use action "refresh" instead:
{{
  "title": "...",
  "steps": [
    {{
      "action":    "refresh",
      "provider":  "aws|azure|gcp",
      "resource":  "<resource name>",
      "args":      ["<cli args without binary or --output flag>"],
      "file_path": "<exact path from Loaded Data Files above>",
      "scope":     {{"Region": "<region>", "Account": "<account>"}}
    }}
  ]
}}

## Rules
1. "filter": jmespath applied to the full records array.
   - Equality:  [?State.Name == 'running']
   - Tag exact: [?Tags[?Key=='Env' && Value=='prod']]
   - Variable from prior step bind: [?VpcId == '{{vpc_id}}']  (use single braces)
   - null means no filter (return all records)
2. "icontains": Python case-insensitive contains on top-level fields.
   ALWAYS use icontains for Account and Region — users say "dev" but the account is "DevelopmentCampaign",
   users say "production" but the account is "Production". NEVER use filter or tag_equals for Account
   or Region. For environment words (production/prod, development/dev, staging, qa), ALWAYS match via
   icontains on Account. Only additionally filter by an Environment tag if the user explicitly mentions a tag.
3. "tag_icontains": case-insensitive contains on tag values. Works for both AWS (Tags array) and Azure (tags dict).
4. "tag_equals": exact match on tag values. Works for both AWS (Tags array) and Azure (tags dict). Prefer this when user specifies an exact value.
5. "columns.path": jmespath on a single record dict.
   - Tag value:    Tags[?Key=='Name'].Value | [0]
   - Nested field: State.Name
   - Top-level:    InstanceId
6. "bind": extract values from results[0] to use in subsequent steps.
   Path is jmespath on a single record (results[0]).
   Use {{var_name}} in subsequent filter strings.
7. "show": set false for steps that only exist to extract bind values.
8. "dedupe_field": deduplicate output rows by this field (e.g. "VpcId").
9. AWS EC2 records have VpcId and SubnetId as top-level fields (not just in Tags).
10. Only generate a step for a resource type if you are confident that resource type
    actually has the required fields or tags to satisfy the filter. Do not speculatively
    query vpc, subnet, eks, or other resources unless the user explicitly asks about them
    or you know those resources carry the needed tag/field.
11. Always include the field(s) used in "filter", "icontains", "tag_icontains", and
    "tag_equals" as display columns. If the user filtered by Owner=sre-ops, the Owner
    column must appear in the results so the match is visible.
12. "count_only": set true when the user asks "how many", "count", or any question
    whose answer is a number. Do not include "columns" when count_only is true.
    The engine will print "{{N}} {{resource}} records match." automatically.
13. "action": defaults to "query". Use "refresh" when the user says "latest", "refresh",
    "update", "sync", or "get latest data". Do not mix query and refresh steps.
14. For "refresh" steps:
    - "args": CLI args without the binary name or --output flag.
      AWS examples:  ["ec2","describe-instances","--region","us-east-1"]
                     ["ec2","describe-instances","--instance-ids","i-0abc","--region","us-east-1"]
      Azure example: ["vm","list","--subscription","MySubscription"]
      GCP example:   ["compute","instances","list","--project","my-project"]
    - "file_path": use the exact path from "Loaded Data Files" above for the matching resource.
      If no file exists yet for this resource/account/region, construct the path following
      the directory structure convention.
    - "scope": used for targeted merge. For a regional refresh set {{"Region":"x","Account":"y"}}.
      For a specific resource (e.g. one instance), set {{"InstanceId":"i-0abc"}} (use the dedup field).
16. NEVER fabricate column values. Only include columns whose paths exist in the field schema above.
    Do not add columns for data not in the schema (e.g. Cost, Price, Billing, Spend).
    Do not mix resources from different providers to answer a single-provider question.
17. When the user asks for data that is not present in any loaded schema — such as cost, pricing,
    billing, or spend — output an unavailable plan so the engine can show a helpful message:
    {{"title": "<descriptive title>", "steps": [], "unavailable": "Cost/pricing data is not in the local snapshot. Switch to live mode with /live to query it in real time."}}
    The engine will display the "unavailable" message directly. Do NOT invent placeholder columns.
15. When the user asks for latest/refresh data about a SPECIFIC resource ID (e.g. an instance ID)
    and you do not already know its Region and Account from prior conversation, you MUST add a
    preliminary query step (show=false) that filters to that resource and binds "region" and
    "account" from its record. Then use {{region}} and {{account}} as placeholders in the refresh
    step's "args", "file_path", and "scope". The engine will substitute the real values before
    running the CLI. NEVER emit a literal placeholder like {{region}} or {{account}} unless you
    are following this two-step pattern.

## Examples

User: list running ec2 instances
{{"title": "Running EC2 Instances", "steps": [{{"resource": "ec2", "filter": "[?State.Name == 'running']", "columns": [{{"header": "Name", "path": "Tags[?Key=='Name'].Value | [0]", "default": "N/A"}}, {{"header": "InstanceId", "path": "InstanceId", "default": "N/A"}}, {{"header": "Type", "path": "InstanceType", "default": "N/A"}}, {{"header": "Account", "path": "Account"}}, {{"header": "Region", "path": "Region"}}, {{"header": "State", "path": "State.Name", "default": "N/A"}}], "show": true}}]}}

User: instances in dev account owned by sre-ops
{{"title": "Instances in dev account owned by sre-ops", "steps": [{{"resource": "ec2", "icontains": {{"Account": "dev"}}, "tag_equals": {{"Owner": "sre-ops"}}, "columns": [{{"header": "Name", "path": "Tags[?Key=='Name'].Value | [0]", "default": "N/A"}}, {{"header": "InstanceId", "path": "InstanceId", "default": "N/A"}}, {{"header": "Account", "path": "Account"}}, {{"header": "Region", "path": "Region"}}, {{"header": "Owner", "path": "Tags[?Key=='Owner'].Value | [0]", "default": "N/A"}}], "show": true}}]}}

User: vpc and subnet details for i-00c08ec21f778c883
{{"title": "VPC and Subnet for i-00c08ec21f778c883", "steps": [{{"resource": "ec2", "filter": "[?InstanceId == 'i-00c08ec21f778c883']", "bind": {{"vpc_id": "VpcId", "subnet_id": "SubnetId"}}, "show": false}}, {{"resource": "vpc", "filter": "[?VpcId == '{{vpc_id}}']", "columns": [{{"header": "VpcId", "path": "VpcId"}}, {{"header": "Name", "path": "Tags[?Key=='Name'].Value | [0]", "default": "N/A"}}, {{"header": "CIDR", "path": "CidrBlock", "default": "N/A"}}, {{"header": "Account", "path": "Account"}}, {{"header": "Region", "path": "Region"}}], "dedupe_field": "VpcId", "show": true}}, {{"resource": "subnet", "filter": "[?SubnetId == '{{subnet_id}}']", "columns": [{{"header": "SubnetId", "path": "SubnetId"}}, {{"header": "Name", "path": "Tags[?Key=='Name'].Value | [0]", "default": "N/A"}}, {{"header": "CIDR", "path": "CidrBlock", "default": "N/A"}}, {{"header": "Account", "path": "Account"}}, {{"header": "Region", "path": "Region"}}], "dedupe_field": "SubnetId", "show": true}}]}}

User: how many running ec2 instances are there?
{{"title": "Running EC2 Instance Count", "steps": [{{"resource": "ec2", "filter": "[?State.Name == 'running']", "count_only": true, "show": true}}]}}

User: give me the count of aws resources in production
{{"title": "AWS Resources in Production - Count", "steps": [{{"resource": "ec2", "icontains": {{"Account": "production"}}, "count_only": true, "show": true}}, {{"resource": "vpc", "icontains": {{"Account": "production"}}, "count_only": true, "show": true}}, {{"resource": "subnet", "icontains": {{"Account": "production"}}, "count_only": true, "show": true}}]}}

User: get latest ec2 data for production us-east-1
{{"title": "Refresh EC2 — Production us-east-1", "steps": [{{"action": "refresh", "provider": "aws", "resource": "ec2", "args": ["ec2", "describe-instances", "--region", "us-east-1"], "file_path": "data/aws/Production/us-east-1/ec2.json", "scope": {{"Region": "us-east-1", "Account": "Production"}}}}]}}

User: refresh data for instance i-0abc123
{{"title": "Refresh EC2 instance i-0abc123", "steps": [{{"action": "refresh", "provider": "aws", "resource": "ec2", "args": ["ec2", "describe-instances", "--instance-ids", "i-0abc123", "--region", "us-east-1"], "file_path": "data/aws/Production/us-east-1/ec2.json", "scope": {{"InstanceId": "i-0abc123"}}}}]}}

User: get latest about i-0abc123  (region/account unknown from conversation)
{{"title": "Refresh EC2 instance i-0abc123", "steps": [{{"action": "query", "resource": "ec2", "filter": "[?InstanceId == 'i-0abc123']", "bind": {{"region": "Region", "account": "Account"}}, "show": false}}, {{"action": "refresh", "provider": "aws", "resource": "ec2", "args": ["ec2", "describe-instances", "--instance-ids", "i-0abc123", "--region", "{{region}}"], "file_path": "data/aws/{{account}}/{{region}}/ec2.json", "scope": {{"InstanceId": "i-0abc123"}}}}]}}

User: show me the cost of all azure resources
{{"title": "Azure Resource Cost", "steps": [], "unavailable": "Cost/pricing data is not in the local snapshot. Switch to live mode with /live to query it in real time."}}
"""
