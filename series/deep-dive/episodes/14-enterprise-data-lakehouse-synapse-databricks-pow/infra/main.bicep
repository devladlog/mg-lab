// Contoso lakehouse landing zone: ADLS Gen2, Azure Databricks (+ access connector), Synapse workspace (serverless SQL).
// Microsoft Purview is deliberately NOT here: classic Purview accounts can no longer be created (see README).
targetScope = 'resourceGroup'

@description('Short lowercase prefix, 3-11 characters, used in resource names.')
@minLength(3)
@maxLength(11)
param prefix string = 'mglab14'
param location string = resourceGroup().location
@allowed(['premium', 'trial'])
@description('trial = Premium with 14 days of free DBUs (needs a pay-as-you-go subscription, not a Free Trial one).')
param databricksSku string = 'premium'
@description('Object id of the person or group that becomes Synapse Microsoft Entra admin.')
param synapseAdminObjectId string
param synapseAdminLogin string = 'labadmin@contoso.example'
param tags object = { project: 'mglab', episode: 'deep-dive-14', owner: 'alex.demo' }

var suffix = uniqueString(resourceGroup().id)
var storageName = take('st${prefix}${suffix}', 24)
var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var blobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource lake 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobSvc 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: lake
  name: 'default'
}

resource lakeContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobSvc
  name: 'lake'
}

resource synapseFs 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobSvc
  name: 'synapse'
}

// Lifecycle: ONLY the raw landing files move to cool. Delta tables (bronze/, silver/, gold/ and every _delta_log)
// are never tiered or archived: archived blobs cannot be read, and an archived _delta_log breaks the table.
resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: lake
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'landing-to-cool'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'], prefixMatch: ['lake/landing/'] }
            actions: { baseBlob: { tierToCool: { daysAfterModificationGreaterThan: 30 } } }
          }
        }
      ]
    }
  }
}

resource connector 'Microsoft.Databricks/accessConnectors@2024-05-01' = {
  name: 'dbac-${prefix}-${suffix}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
}

resource connectorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: lake
  name: guid(lake.id, connector.id, blobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
    principalId: connector.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource databricks 'Microsoft.Databricks/workspaces@2024-05-01' = {
  name: 'dbw-${prefix}-${suffix}'
  location: location
  tags: tags
  sku: { name: databricksSku }
  properties: {
    managedResourceGroupId: subscriptionResourceId('Microsoft.Resources/resourceGroups', 'rg-${prefix}-dbw-managed-${suffix}')
    publicNetworkAccess: 'Enabled'
  }
}

resource synapse 'Microsoft.Synapse/workspaces@2021-06-01' = {
  name: 'syn-${prefix}-${suffix}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    defaultDataLakeStorage: {
      accountUrl: lake.properties.primaryEndpoints.dfs
      filesystem: synapseFs.name
    }
    azureADOnlyAuthentication: true
    publicNetworkAccess: 'Enabled'
  }
}

resource synapseAdmin 'Microsoft.Synapse/workspaces/administrators@2021-06-01' = {
  parent: synapse
  name: 'activeDirectory'
  properties: {
    administratorType: 'ActiveDirectory'
    login: synapseAdminLogin
    sid: synapseAdminObjectId
    tenantId: tenant().tenantId
  }
}

// Serverless SQL reads the lake as the CALLER (Entra pass-through), so grant readers at the storage account.
resource adminReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: lake
  name: guid(lake.id, synapseAdminObjectId, blobDataReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataReader)
    principalId: synapseAdminObjectId
    principalType: 'User'
  }
}

output storageAccount string = lake.name
output lakeUrl string = '${lake.properties.primaryEndpoints.dfs}lake'
output databricksWorkspaceUrl string = databricks.properties.workspaceUrl
output accessConnectorId string = connector.id
output synapseServerlessEndpoint string = synapse.properties.connectivityEndpoints.sqlOnDemand
