// DEVLADLOG AI #10: one Azure OpenAI account for a screenshot + voice note -> ticket pipeline, keyless.
//  - Sweden Central: Standard deployments for gpt-4.1-mini (vision), whisper and tts are listed there on Learn
//    (models > region availability). Check again before deploying: availability changes.
//  - Keys off, custom subdomain: callers use Entra ID. The developer gets Cognitive Services OpenAI User (inference only).
// Deployments are created one after another: parallel writes to one account can fail with a conflict.

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-mm'
param location string = 'swedencentral'
@description('Object ID of the person (or group) who runs the demo. Empty = no role assignment.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'
param visionModel string = 'gpt-4.1-mini'
param visionVersion string = '2025-04-14'
@description('Thousands of tokens per minute. Small on purpose: this is a demo.')
param visionCapacity int = 50
param whisperCapacity int = 3
param ttsCapacity int = 3

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

resource vision 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: 'vision'
  sku: { name: 'Standard', capacity: visionCapacity }
  properties: {
    model: { format: 'OpenAI', name: visionModel, version: visionVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource whisper 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: 'whisper'
  sku: { name: 'Standard', capacity: whisperCapacity }
  properties: {
    model: { format: 'OpenAI', name: 'whisper', version: '001' }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  dependsOn: [vision]
}

resource tts 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: 'tts'
  sku: { name: 'Standard', capacity: ttsCapacity }
  properties: {
    model: { format: 'OpenAI', name: 'tts', version: '001' }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  dependsOn: [whisper]
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
output deployments array = [vision.name, whisper.name, tts.name]
