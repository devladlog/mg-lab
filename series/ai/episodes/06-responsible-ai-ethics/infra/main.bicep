// DEVLADLOG AI #6: guardrails as code for the HR bot, keyless.
//  - Azure AI Content Safety (F0 by default): the app-level guard (Prompt Shields + harm categories)
//  - Azure OpenAI with a custom guardrail policy (raiPolicies) attached to the gpt-5-mini deployment:
//    core harms blocked at Medium on input and output, user prompt attacks (Jailbreak) and document attacks
//    (Indirect Attack, off in the default policy) on, protected material checks on the output
//  - the developer gets Cognitive Services User (Content Safety) and Cognitive Services OpenAI User (model)

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-rai'
param location string = resourceGroup().location
@description('Object ID of the person (or group) who runs the gate. Empty = no role assignments.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'
@allowed(['F0', 'S0'])
param contentSafetySku string = 'F0'

param policyName string = 'contoso-hr-strict'
param chatDeployment string = 'chat'
param chatModel string = 'gpt-5-mini'
param chatVersion string = '2025-08-07'
@allowed(['GlobalStandard', 'DataZoneStandard', 'Standard'])
param chatSku string = 'DataZoneStandard'
param chatCapacity int = 20

var suffix = take(uniqueString(resourceGroup().id), 6)
var safetyName = '${prefix}-cs-${suffix}'
var aoaiName = '${prefix}-aoai-${suffix}'
var roles = {
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  openAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
}
// Core harms: severityThreshold 'Medium' blocks medium and high (the default level). Read the README gotcha before
// changing it: the new Foundry portal names its blocking levels differently.
var contentFilters = [
  { name: 'Hate', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Sexual', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Violence', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Selfharm', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Jailbreak', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Indirect Attack', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Hate', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Sexual', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Violence', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Selfharm', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Protected Material Text', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Protected Material Code', blocking: false, enabled: true, source: 'Completion' }
]

resource safety 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: safetyName
  location: location
  kind: 'ContentSafety'
  sku: { name: contentSafetySku }
  properties: {
    customSubDomainName: safetyName // required for Entra ID tokens
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

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

resource policy 'Microsoft.CognitiveServices/accounts/raiPolicies@2025-06-01' = {
  parent: aoai
  name: policyName
  properties: {
    mode: 'Default'
    basePolicyName: 'Microsoft.DefaultV2'
    contentFilters: contentFilters
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: chatDeployment
  sku: { name: chatSku, capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModel, version: chatVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: policy.name
  }
}

resource devToSafety 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(safety.id, developerPrincipalId, roles.cognitiveServicesUser)
  scope: safety
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

resource devToOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(aoai.id, developerPrincipalId, roles.openAiUser)
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.openAiUser)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output safetyEndpoint string = 'https://${safety.name}.cognitiveservices.azure.com/'
output aoaiEndpoint string = 'https://${aoai.name}.openai.azure.com'
output safetyName string = safety.name
output aoaiName string = aoai.name
output chatDeployment string = chat.name
output policyName string = policy.name
