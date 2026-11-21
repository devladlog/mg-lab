// One Azure OpenAI account with one model deployment. Key authentication is disabled: callers must use
// Microsoft Entra ID and hold "Cognitive Services OpenAI User" on this account.

@description('Account name; also used as the custom subdomain (required for Entra ID auth).')
param name string
param location string
param deploymentName string
param modelName string
param modelVersion string
@allowed(['GlobalStandard', 'DataZoneStandard', 'Standard'])
param deploymentSku string
@description('Deployment capacity in units of 1,000 tokens per minute.')
@minValue(1)
param capacity int
@allowed(['Enabled', 'Disabled'])
param publicNetworkAccess string = 'Enabled'
@description('Who gets "Cognitive Services OpenAI User": [{ id: <principalId>, type: \'ServicePrincipal\' | \'User\' | \'Group\' }].')
param inferencePrincipals array = []
param tags object = {}

// Built-in role "Cognitive Services OpenAI User" (inference only; can't read keys or change deployments).
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  tags: tags
  properties: {
    customSubDomainName: name
    disableLocalAuth: true
    publicNetworkAccess: publicNetworkAccess
    networkAcls: { defaultAction: publicNetworkAccess == 'Enabled' ? 'Allow' : 'Deny' }
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: deploymentName
  sku: { name: deploymentSku, capacity: capacity }
  properties: {
    model: { format: 'OpenAI', name: modelName, version: modelVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

// principalType matters for a managed identity created in the same deployment: without it, the assignment can
// fail while the new identity is still replicating in Entra ID.
resource inferenceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in inferencePrincipals: {
  name: guid(account.id, p.id, openAiUserRoleId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: p.id
    principalType: p.type
  }
}]

output id string = account.id
output name string = account.name
output endpoint string = 'https://${name}.openai.azure.com'
