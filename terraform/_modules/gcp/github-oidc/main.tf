terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~>5.0" }
  }
}

# TODO: google_iam_workload_identity_pool,
#        google_iam_workload_identity_pool_provider (OIDC, GitHub token claims),
#        google_service_account, google_service_account_iam_binding (workloadIdentityUser),
#        google_project_iam_member (roles/artifactregistry.writer on AR repo)
#
# GitHub Actions usage:
#   - uses: google-github-actions/auth@v2
#     with:
#       workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
#       service_account: ${{ secrets.WIF_SERVICE_ACCOUNT }}
