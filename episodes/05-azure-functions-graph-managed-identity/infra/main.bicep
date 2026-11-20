// MG Lab #5 — Azure Function (Flex Consumption) + system-assigned managed identity. No secrets anywhere:
// the host reaches its storage with the identity (shared keys disabled) and calls Microsoft Graph with the same identity.
@description('Azure region')
param location string = resourceGroup().location

@description('Graph site id of the SharePoint site: <host>,<site-collection-guid>,<web-guid>')
param sharePointSiteId string

@description('SharePoint list to read')
param sharePointList string = 'Project Requests'

var suffix = uniqueString(resourceGroup().id)
var functionAppName = 'func-mglab-graph-${suffix}'
var storageName = 'stmglab${suffix}'
var deploymentContainer = 'deployments'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowSharedKeyAccess: false        // identity only
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
  resource blob 'blobServices' = {
    name: 'default'
    resource container 'containers' = { name: deploymentContainer }
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-mglab-graph-${suffix}'
  location: location
  kind: 'functionapp'
  sku: { tier: 'FlexConsumption', name: 'FC1' }
  properties: { reserved: true }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'AzureWebJobsStorage__accountName', value: storage.name }
        { name: 'SHAREPOINT_SITE_ID', value: sharePointSiteId }
        { name: 'SHAREPOINT_LIST', value: sharePointList }
      ]
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainer}'
          authentication: { type: 'SystemAssignedIdentity' }
        }
      }
      scaleAndConcurrency: { maximumInstanceCount: 40, instanceMemoryMB: 2048 }
      runtime: { name: 'dotnet-isolated', version: '8.0' }
    }
  }
}

// The identity needs data-plane roles on its own storage (blobs for deployment + host locks, queues/tables for the host).
var storageRoles = [
  'b7e6dc6d-f1e8-4753-8033-0f276bb0955b' // Storage Blob Data Owner
  '974c5e8b-45b9-4653-ba55-5f855dd0fb88' // Storage Queue Data Contributor
  '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3' // Storage Table Data Contributor
]
resource storageRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for roleId in storageRoles: {
  name: guid(storage.id, functionApp.id, roleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}]

output functionAppName string = functionApp.name
output principalId string = functionApp.identity.principalId
output defaultHostName string = functionApp.properties.defaultHostName
