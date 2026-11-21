// Lab resource group rg-mglab-powerapps-14: one Azure OpenAI resource with one Standard deployment, one Key Vault for the Claude API key
// (a secret environment variable needs one), and the role assignments for the lab user and, optionally, the Dataverse service principal.
// Deploy:  az deployment group create -g rg-mglab-powerapps-14 -f main.bicep -p principalId=<object id of the lab user>
// Tear down: az group delete -n rg-mglab-powerapps-14 --yes   (deleting the group removes everything below)
targetScope = 'resourceGroup'

@description('Region. Sweden Central offers the Standard deployment of the default model on the day of research; check the model catalogue before you deploy.')
param location string = 'swedencentral'

@description('Globally unique custom subdomain. Entra ID (token) sign-in needs a custom subdomain, the regional endpoint will not do.')
@minLength(2)
@maxLength(24)
param accountName string = 'oai-mglab-pa14-${take(uniqueString(resourceGroup().id), 5)}'

@description('Model to deploy. The default was Deprecated in the catalogue (retirement 2027-04-14) when this was written: pick a current model if the deployment is refused.')
param modelName string = 'gpt-4.1-mini'

@description('Model version, as listed in the catalogue for the region.')
param modelVersion string = '2025-04-14'

@description('Name callers use as "model" in the request.')
param deploymentName string = 'triage'

@description('Capacity in thousands of tokens per minute for the Standard SKU. 10 is plenty for 13 golden cases and a demo.')
@minValue(1)
@maxValue(50)
param capacityK int = 10

@description('Object id of the lab user (Entra) who gets Cognitive Services OpenAI User. Not a secret.')
param principalId string

@description('Key Vault name (3 to 24 characters, globally unique).')
@minLength(3)
@maxLength(24)
param keyVaultName string = 'kv-mglab-pa14-${take(uniqueString(resourceGroup().id), 5)}'

@description('Object id of the "Dataverse" enterprise application in the lab tenant (application id 00000007-0000-0000-c000-000000000000). Leave empty to grant it by hand in the portal.')
param dataverseServicePrincipalId string = ''

// Built-in roles. "Cognitive Services OpenAI User" is on Learn's built-in roles page; Key Vault Secrets Officer / Secrets User: see README "Unverified".
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
// Built-in role "Cognitive Services OpenAI User"
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
  tags: {
    purpose: 'devladlog-powerapps-14'
    teardown: 'delete the resource group'
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: account
  name: deploymentName
  sku: {
    name: 'Standard'
    capacity: capacityK
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
}

resource userRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: account
  name: guid(account.id, principalId, openAiUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: principalId
    principalType: 'User'
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    purpose: 'devladlog-powerapps-14'
    teardown: 'delete the resource group, then purge the soft-deleted vault'
  }
}

resource vaultOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, principalId, keyVaultSecretsOfficerRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
    principalId: principalId
    principalType: 'User'
  }
}

resource vaultDataverse 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(dataverseServicePrincipalId)) {
  scope: vault
  name: guid(vault.id, dataverseServicePrincipalId, keyVaultSecretsUserRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: dataverseServicePrincipalId
    principalType: 'ServicePrincipal'
  }
}

output endpoint string = account.properties.endpoint
output deployment string = deployment.name
output keyVault string = vault.name
