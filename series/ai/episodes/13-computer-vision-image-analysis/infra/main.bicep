// DEVLADLOG AI #13: one Azure Vision (Computer Vision) resource for Image Analysis 4.0, keyless.
//  - kind 'ComputerVision' is the single-service Vision resource; F0 is the free tier (Learn quickstarts), S1 is paid.
//  - West Europe supports Image Analysis 4.0 including Captions (Learn, "Region availability").
//  - Custom subdomain + disableLocalAuth: callers use Entra ID (Learn: Entra needs the custom subdomain endpoint).
//  - Role: Cognitive Services User (a97b65f3-...). Learn describes it as "read and list keys"; with local auth off there
//    are no usable keys. Whether a narrower built-in role covers the imageanalysis data action is not documented on
//    the pages we checked, so we use this one and say so.

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-vis'
param location string = 'westeurope'
@allowed(['F0', 'S1'])
param skuName string = 'F0'
@description('Object ID of the person (or group) who runs the demo. Empty = no role assignment.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'

var suffix = take(uniqueString(resourceGroup().id), 6)
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource vision 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${prefix}-${suffix}'
  location: location
  kind: 'ComputerVision'
  sku: { name: skuName }
  properties: {
    customSubDomainName: '${prefix}-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource devToAccount 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(vision.id, developerPrincipalId, cognitiveServicesUser)
  scope: vision
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output visionEndpoint string = vision.properties.endpoint
output visionName string = vision.name
