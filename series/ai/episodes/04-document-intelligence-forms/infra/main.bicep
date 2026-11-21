// DEVLADLOG AI #4: one Document Intelligence resource, keyless.
// Learn: Microsoft Entra authentication needs a single-service resource with a custom subdomain (regional
// endpoints don't support it); callers need "Cognitive Services User" on the resource.

@description('Short prefix for the resource name (a unique suffix is appended).')
param prefix string = 'mglab-docintel'
param location string = resourceGroup().location
@description('F0 = free tier: first 2 pages per document, 4 MB per file, 1 analyze and 1 get request per second.')
@allowed(['F0', 'S0'])
param sku string = 'F0'
@description('Object ID of the developer (or group) running the scripts. Empty = no role assignment.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'

var name = '${prefix}-${take(uniqueString(resourceGroup().id), 6)}'
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource docintel 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  kind: 'FormRecognizer'
  sku: { name: sku }
  properties: {
    customSubDomainName: name // required for Entra ID auth
    disableLocalAuth: true    // keys stop working
    publicNetworkAccess: 'Enabled'
  }
}

resource devRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(docintel.id, developerPrincipalId, cognitiveServicesUser)
  scope: docintel
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output endpoint string = docintel.properties.endpoint
output name string = docintel.name
