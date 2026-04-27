locals {
  oidc_url = "https://token.actions.githubusercontent.com"
}

# ── GitHub OIDC Provider ──────────────────────────────────────────────────────
# Only create once per AWS account.  Set create_oidc_provider=false in prod
# if dev and prod share the same account.

data "tls_certificate" "github" {
  count = var.create_oidc_provider ? 1 : 0
  url   = local.oidc_url
}

resource "aws_iam_openid_connect_provider" "github" {
  count           = var.create_oidc_provider ? 1 : 0
  url             = local.oidc_url
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github[0].certificates[0].sha1_fingerprint]
  tags            = merge({ Name = "${var.project}-github-oidc" }, var.tags)
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = local.oidc_url
}

locals {
  oidc_provider_arn = var.create_oidc_provider? aws_iam_openid_connect_provider.github[0].arn: data.aws_iam_openid_connect_provider.github[0].arn
}

# ── IAM Role for GitHub Actions ───────────────────────────────────────────────

data "aws_iam_policy_document" "github_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scope to this repository only — prevents other repos assuming this role
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project}-${var.environment}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
  tags               = merge({ Name = "${var.project}-${var.environment}-github-actions" }, var.tags)
}

# ── ECR Push Policy ───────────────────────────────────────────────────────────

data "aws_iam_policy_document" "ecr_push" {
  # GetAuthorizationToken is account-scoped (no resource restriction allowed)
  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = var.ecr_repository_arns
  }
}

resource "aws_iam_policy" "ecr_push" {
  name   = "${var.project}-${var.environment}-github-ecr-push"
  policy = data.aws_iam_policy_document.ecr_push.json
  tags   = merge({ Name = "${var.project}-${var.environment}-github-ecr-push" }, var.tags)
}

resource "aws_iam_role_policy_attachment" "ecr_push" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.ecr_push.arn
}
