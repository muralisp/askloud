# ─────────────────────────────────────────────────────────────────────────────
# ASKLOUD INVENTORY AGENT — Satellite resources in the workload (dev) account
#
# Cross-account flow:
#
#   Workload Account (this workspace)      Central Account (central_ops/)
#   ────────────────────────────────────   ──────────────────────────────────
#   S3 state bucket
#     └─ EventBridge notification ON
#         └─ Default event bus
#               └─ Rule (*.tfstate)
#                   └─ PutEvents ────────► askloud-central-bus
#                                               └─ Rule → Diff Lambda
#                                                             └─ SQS
#                                                                 └─ Router Lambda
#                                                                       └─ sts:AssumeRole
#   Askloud-Inventory-Reader ◄──────────────────────────────────────────┘
#     └─ ec2:Describe*, rds:Describe*, …
#
# ─────────────────────────────────────────────────────────────────────────────

# ── Cross-account IAM role ────────────────────────────────────────────────────
data "aws_iam_policy_document" "inventory_reader_trust" {
  statement {
    sid    = "AllowCentralRouterLambdaAssume"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.router_lambda_role_arn]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "inventory_reader" {
  name                 = "Askloud-Inventory-Reader"
  description          = "Read-only cross-account role assumed by the Askloud Router Lambda for cloud inventory discovery"
  assume_role_policy   = data.aws_iam_policy_document.inventory_reader_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "inventory_reader_permissions" {
  statement {
    sid    = "EC2ReadOnly"
    effect = "Allow"
    actions = [
      "ec2:DescribeInstances", "ec2:DescribeImages", "ec2:DescribeVolumes",
      "ec2:DescribeSnapshots", "ec2:DescribeSecurityGroups", "ec2:DescribeVpcs",
      "ec2:DescribeSubnets", "ec2:DescribeRouteTables", "ec2:DescribeInternetGateways",
      "ec2:DescribeNatGateways", "ec2:DescribeNetworkInterfaces", "ec2:DescribeAddresses",
      "ec2:DescribeKeyPairs", "ec2:DescribeTags", "ec2:DescribeAvailabilityZones",
      "ec2:DescribeRegions",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "RDSReadOnly"
    effect = "Allow"
    actions = [
      "rds:DescribeDBInstances", "rds:DescribeDBClusters", "rds:DescribeDBSubnetGroups",
      "rds:DescribeDBParameterGroups", "rds:DescribeDBSnapshots", "rds:ListTagsForResource",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "IAMReadOnly"
    effect = "Allow"
    actions = [
      "iam:GetAccountSummary", "iam:GetRole", "iam:GetRolePolicy", "iam:GetUser",
      "iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListRoles", "iam:ListUsers",
      "iam:ListPolicies", "iam:ListAttachedRolePolicies", "iam:ListRolePolicies",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "S3MetadataReadOnly"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation", "s3:GetBucketTagging", "s3:GetBucketVersioning",
      "s3:GetBucketPolicy", "s3:GetEncryptionConfiguration",
      "s3:GetBucketPublicAccessBlock", "s3:ListAllMyBuckets",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "EKSReadOnly"
    effect = "Allow"
    actions = [
      "eks:DescribeCluster", "eks:ListClusters",
      "eks:DescribeNodegroup", "eks:ListNodegroups",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "LambdaReadOnly"
    effect    = "Allow"
    actions   = ["lambda:ListFunctions", "lambda:GetFunction", "lambda:ListTags"]
    resources = ["*"]
  }

  statement {
    sid       = "TaggingReadOnly"
    effect    = "Allow"
    actions   = ["tag:GetResources", "tag:GetTagKeys", "tag:GetTagValues"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "inventory_reader" {
  name   = "Askloud-Inventory-Reader-Policy"
  role   = aws_iam_role.inventory_reader.id
  policy = data.aws_iam_policy_document.inventory_reader_permissions.json
}

# ── S3 state bucket → EventBridge ─────────────────────────────────────────────
data "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name
}

resource "aws_s3_bucket_notification" "state_to_eventbridge" {
  bucket      = data.aws_s3_bucket.state.id
  eventbridge = true
}

# Grant the central Diff Lambda cross-account read access to *.tfstate objects.
# Without this resource policy, cross-account s3:GetObject is denied even when
# the Lambda's identity policy allows it.
data "aws_iam_policy_document" "tfstate_bucket_policy" {
  statement {
    sid    = "AllowDiffLambdaReadTFState"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.diff_lambda_role_arn]
    }

    actions   = ["s3:GetObject"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${var.state_bucket_name}/*.tfstate"]
  }
}

resource "aws_s3_bucket_policy" "tfstate" {
  bucket = data.aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.tfstate_bucket_policy.json
}

# ── EventBridge forwarding role ────────────────────────────────────────────────
data "aws_iam_policy_document" "eventbridge_forwarding_trust" {
  statement {
    sid    = "AllowEventBridgeService"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]

    # Prevent confused-deputy: only rules in this account may use this role
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "eventbridge_forwarding" {
  name               = "${var.project}-${var.environment}-eventbridge-forwarding"
  description        = "Allows workload EventBridge to forward .tfstate events to the Askloud central bus"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_forwarding_trust.json
}

data "aws_iam_policy_document" "eventbridge_forwarding_permissions" {
  statement {
    sid       = "PutEventsToCentralBus"
    effect    = "Allow"
    actions   = ["events:PutEvents"]
    resources = [var.central_event_bus_arn]
  }
}

resource "aws_iam_role_policy" "eventbridge_forwarding" {
  name   = "${var.project}-${var.environment}-eventbridge-forwarding-policy"
  role   = aws_iam_role.eventbridge_forwarding.id
  policy = data.aws_iam_policy_document.eventbridge_forwarding_permissions.json
}

# ── EventBridge rule: default bus → central bus ───────────────────────────────
resource "aws_cloudwatch_event_rule" "forward_tfstate_events" {
  name        = "${var.project}-${var.environment}-forward-tfstate-to-central"
  description = "Forward S3 ObjectCreated *.tfstate events to the Askloud central EventBridge bus"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [var.state_bucket_name] }
      object = { key = [{ suffix = ".tfstate" }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "forward_to_central_bus" {
  rule      = aws_cloudwatch_event_rule.forward_tfstate_events.name
  target_id = "AskloudCentralBusTarget"
  arn       = var.central_event_bus_arn
  role_arn  = aws_iam_role.eventbridge_forwarding.arn

  depends_on = [aws_iam_role_policy.eventbridge_forwarding]
}

# ── EventBridge rule: EC2 terminated → central bus ────────────────────────────
# Catches instances terminated via any mechanism (console, CLI, autoscaling,
# terraform destroy) so the inventory is updated without waiting for a tfstate
# write to S3.
resource "aws_cloudwatch_event_rule" "forward_ec2_terminated" {
  name        = "${var.project}-${var.environment}-forward-ec2-terminated"
  description = "Forward EC2 instance terminal state events to the Askloud central EventBridge bus"

  event_pattern = jsonencode({
    source      = ["aws.ec2"]
    detail-type = ["EC2 Instance State-change Notification"]
    detail = {
      state = ["shutting-down", "terminated"]
    }
  })
}

resource "aws_cloudwatch_event_target" "ec2_terminated_to_central_bus" {
  rule      = aws_cloudwatch_event_rule.forward_ec2_terminated.name
  target_id = "AskloudCentralBusEC2Target"
  arn       = var.central_event_bus_arn
  role_arn  = aws_iam_role.eventbridge_forwarding.arn

  depends_on = [aws_iam_role_policy.eventbridge_forwarding]
}
