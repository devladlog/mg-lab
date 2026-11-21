// DEVLADLOG AI #12: one Azure Language resource (preconfigured features: language detection, PII, sentiment and opinion
// mining, key phrases, NER), keyless.
//  - kind 'TextAnalytics' is the Language resource ("Create language" in the portal). Free F0 gives 5,000 text records a month
//    (Learn). Learn's limits pages for the custom features say one F0 Language resource per subscription: if one already
//    exists, deploy with skuName 'S' (Learn: S also starts with 5,000 free text records before charging).
//  - West Europe: Learn says most Language capabilities, including all the preconfigured ones, are available in the
//    supported regions, and that Language does not store or process customer data outside the region you deploy it in.
//  - Keys off + custom subdomain: callers use Entra ID (Learn: Entra needs the custom subdomain endpoint).
//  - Role: Cognitive Services Language Reader. Learn's role definition lists the Language analyze-text data action (the
//    synchronous call this episode makes) and read-only authoring; it cannot create projects or deployments.

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-nlp'
param location string = 'westeurope'
@allowed(['F0', 'S'])
param skuName string = 'F0'
@description('Object ID of the person (or group) who runs the demo. Empty = no role assignment.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'

var suffix = take(uniqueString(resourceGroup().id), 6)
var languageReader = '7628b7b8-a8b2-4cdc-b46f-e9b35248918e' // Cognitive Services Language Reader

resource language 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${prefix}-lang-${suffix}'
  location: location
  kind: 'TextAnalytics'
  sku: { name: skuName }
  properties: {
    customSubDomainName: '${prefix}-lang-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource devToAccount 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(language.id, developerPrincipalId, languageReader)
  scope: language
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', languageReader)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output languageEndpoint string = language.properties.endpoint
output languageName string = language.name
