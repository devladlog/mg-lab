// DEVLADLOG AI #5: one Azure OpenAI account for the agent demo, keyless.
//  - custom subdomain (required for Entra ID tokens), local (key) auth disabled
//  - one pinned gpt-5-mini deployment (Responses API + function calling)
//  - the developer who runs the agent gets Cognitive Services OpenAI User (data plane only)

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-agent'
param location string = resourceGroup().location
@description('Object ID of the person (or group) who runs the agent. Empty = no role assignment.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'

param chatDeployment string = 'chat'
param chatModel string = 'gpt-5-mini'
param chatVersion string = '2025-08-07'
@allowed(['GlobalStandard', 'DataZoneStandard', 'Standard'])
param chatSku string = 'DataZoneStandard'
@description('Capacity in thousands of tokens per minute.')
param chatCapacity int = 20

var suffix = take(uniqueString(resourceGroup().id), 6)
var aoaiName = '${prefix}-aoai-${suffix}'
var openAiUserRole = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User

resource aoai 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aoaiName
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: aoaiName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: chatDeployment
  sku: { name: chatSku, capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModel, version: chatVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource devToOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(aoai.id, developerPrincipalId, openAiUserRole)
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRole)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output aoaiEndpoint string = 'https://${aoai.name}.openai.azure.com'
output aoaiName string = aoai.name
output chatDeployment string = chat.name
