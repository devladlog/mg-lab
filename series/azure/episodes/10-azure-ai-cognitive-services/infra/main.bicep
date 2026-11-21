// DEVLADLOG Azure #10: an Azure AI Language resource on the free tier (F0) with key access switched off.
// The only way in is Microsoft Entra ID, and the only permission granted is "Cognitive Services Language Reader",
// which Learn lists with the data action Language/analyze-text/action (what the triage app calls).
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param tags object = {
  workload: 'contoso-support-triage'
  environment: 'lab'
}

@description('Resource name; also the custom subdomain, which Entra ID authentication requires. Globally unique.')
param accountName string = 'lang-triage-${uniqueString(resourceGroup().id)}'

@description('Object ID of the identity that may call the service (deploy.sh passes the signed-in user). Empty: no role is assigned.')
param principalId string = ''

@allowed(['User', 'ServicePrincipal', 'Group'])
param principalType string = 'User'

// Built-in role "Cognitive Services Language Reader" (Learn, built-in roles for AI + machine learning).
var languageReaderRoleId = '7628b7b8-a8b2-4cdc-b46f-e9b35248918e'

resource language 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'TextAnalytics'
  sku: { name: 'F0' } // free tier: 5,000 text records a month, one F0 Language resource per subscription
  properties: {
    customSubDomainName: accountName
    disableLocalAuth: true // no keys: Entra ID only
    publicNetworkAccess: 'Enabled'
  }
}

resource callerCanAnalyze 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(language.id, principalId, languageReaderRoleId)
  scope: language
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', languageReaderRoleId)
    principalId: principalId
    principalType: principalType
  }
}

output accountName string = language.name
output endpoint string = language.properties.endpoint
output location string = language.location
