// DEVLADLOG AI #11: one Azure OpenAI account with one chat deployment for the service-desk chatbot, keyless.
//  - Sweden Central: gpt-4.1-mini is listed as a Standard deployment there on Learn (Foundry Models sold by Azure,
//    "Supported Standard deployment regions"). Check again before deploying: availability changes.
//  - Keys off, custom subdomain: callers use Entra ID. The developer gets Cognitive Services OpenAI User (inference only).

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-bot'
param location string = 'swedencentral'
@description('Object ID of the person (or group) who runs the demo. Empty = no role assignment.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'
param chatModel string = 'gpt-4.1-mini'
param chatVersion string = '2025-04-14'
@description('Thousands of tokens per minute. Small on purpose: this is a demo.')
param chatCapacity int = 50

var suffix = take(uniqueString(resourceGroup().id), 6)
var openAiUser = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User

resource aoai 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${prefix}-aoai-${suffix}'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${prefix}-aoai-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: 'chat'
  sku: { name: 'Standard', capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModel, version: chatVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource devToAccount 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(aoai.id, developerPrincipalId, openAiUser)
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUser)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output aoaiEndpoint string = 'https://${aoai.name}.openai.azure.com'
output aoaiName string = aoai.name
output deployment string = chat.name
