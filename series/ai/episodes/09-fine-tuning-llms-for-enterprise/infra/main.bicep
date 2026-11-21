// DEVLADLOG AI #9: the place where the HR bot's triage model is fine-tuned, keyless.
//  - One Azure OpenAI account in Sweden Central (supports Standard fine-tuning for gpt-4.1-mini and Standard
//    deployments, so training data stays in the region) with keys off and a custom subdomain
//  - The BASE deployment `base` = gpt-4.1-mini 2025-04-14 (the baseline we compare against), version pinned
//  - Fine-tuning access for the developer: Cognitive Services OpenAI Contributor (Learn: fine-tuning needs it;
//    it also covers inference calls and deployment writes on this account)
// The fine-tuned model doesn't exist yet, so its deployment is created later by `python -m fttriage deploy`.

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-ft'
@description('Sweden Central supports Standard training and Standard deployments for gpt-4.1-mini (Learn: fine-tuning overview).')
param location string = 'swedencentral'
@description('Object ID of the person (or group) who fine-tunes. Empty = no role assignment.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'
param baseModel string = 'gpt-4.1-mini'
param baseVersion string = '2025-04-14'
@allowed(['Standard', 'GlobalStandard', 'DataZoneStandard'])
param baseSku string = 'Standard'
param baseCapacity int = 50

var suffix = take(uniqueString(resourceGroup().id), 6)
var openAiContributor = 'a001fd3d-188f-4b5d-821b-7da978bf7442' // Cognitive Services OpenAI Contributor

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

resource base 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: 'base'
  sku: { name: baseSku, capacity: baseCapacity }
  properties: {
    model: { format: 'OpenAI', name: baseModel, version: baseVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource devToAccount 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(aoai.id, developerPrincipalId, openAiContributor)
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiContributor)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output aoaiEndpoint string = 'https://${aoai.name}.openai.azure.com'
output aoaiName string = aoai.name
output baseDeployment string = base.name
