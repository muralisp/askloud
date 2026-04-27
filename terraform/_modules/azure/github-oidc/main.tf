terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~>3.0" }
    azuread = { source = "hashicorp/azuread", version = "~>2.0" }
  }
}

# TODO: azuread_application, azuread_service_principal,
#        azuread_application_federated_identity_credential
#          (subject = "repo:<org>/<repo>:ref:refs/heads/<branch>"),
#        azurerm_role_assignment (AcrPush on ACR resource)
#
# GitHub Actions usage:
#   - uses: azure/login@v2
#     with:
#       client-id: ${{ secrets.AZURE_CLIENT_ID }}
#       tenant-id: ${{ secrets.AZURE_TENANT_ID }}
#       subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
