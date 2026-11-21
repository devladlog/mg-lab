// DEVLADLOG AI #17: ONE Foundry resource (kind AIServices) for every prebuilt Azure AI service of the series,
// keyless, with its logs and metrics going to Log Analytics, and one data-plane role for the person who runs the demo.
//  - kind 'AIServices' is the multi-service Foundry resource (Learn: "Be sure to create one with the kind of AIServices").
//  - customSubDomainName + disableLocalAuth: callers use Microsoft Entra ID; Learn says Entra only works against the custom
//    subdomain and that organisations using Entra should disable local (key) authentication.
//  - Role: Cognitive Services User (Learn: data actions Microsoft.CognitiveServices/*, plus read of metrics and diagnostic
//    settings). Owner and Contributor have management permissions only, so without this role every keyless call is a 403.
//  - Diagnostic settings: categories Audit and RequestResponse plus AllMetrics (Learn: supported logs and metrics for
//    Microsoft.CognitiveServices/accounts). 'Trace' is left off on purpose.
//  - publicNetworkAccess stays Enabled for the demo; Learn calls 'All networks' a setting for prototypes (the audit warns).

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-ai17'
param location string = 'westeurope'
@description('Object ID of the person (or group) who runs the demo. Empty = no role assignment (shows the 403).')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'
@minValue(30)
@maxValue(730)
param logRetentionDays int = 30
param tags object = {
  owner: 'lab'
  costcenter: 'mglab'
  episode: 'ai-17'
}

var suffix = take(uniqueString(resourceGroup().id), 6)
var name = '${prefix}-${suffix}'
var cognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908' // Cognitive Services User

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-log'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: logRetentionDays
  }
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: name
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: foundry
  properties: {
    workspaceId: workspace.id
    logs: [
      { category: 'Audit', enabled: true }
      { category: 'RequestResponse', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

resource developerUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(foundry.id, developerPrincipalId, cognitiveServicesUser)
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUser)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output endpoint string = foundry.properties.endpoint
output resourceId string = foundry.id
output accountName string = foundry.name
output workspaceName string = workspace.name
