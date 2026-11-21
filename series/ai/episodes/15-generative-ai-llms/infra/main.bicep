// DEVLADLOG AI #15: one Azure OpenAI account with one small Standard deployment of a NON-reasoning model, keyless.
//  - gpt-4.1-mini 2025-04-14: logprobs, top_logprobs, temperature and seed are supported (they are listed as
//    unsupported for reasoning models on Learn). Standard in Sweden Central per Learn's region table (checked 21 Nov 2026):
//    check again before deploying, availability moves.
//  - Keys off, custom subdomain: callers use Entra ID. The developer gets Cognitive Services OpenAI User (inference only).

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-gen'
param location string = 'swedencentral'
@description('Object ID of the person (or group) who runs the demo. Empty = no role assignment.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'
param model string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
@description('Thousands of tokens per minute. Small on purpose: this is a demo.')
param capacity int = 50

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
  sku: { name: 'Standard', capacity: capacity }
  properties: {
    model: { format: 'OpenAI', name: model, version: modelVersion }
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
