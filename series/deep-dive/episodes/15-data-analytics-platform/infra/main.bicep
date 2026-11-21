// DEVLADLOG Deep Dive #15: Contoso purchase-request analytics.
// Source: Azure SQL Database (free offer). Lake: ADLS Gen2. Ingestion: Data Factory (managed identity, no secrets).
// Serving: Synapse workspace, used ONLY for its serverless SQL endpoint (pay per data processed, nothing running idle).
// Lab cost for a recording day: well under 1 EUR (see demo.md). Delete the resource group afterwards.

targetScope = 'resourceGroup'

@description('Region for all resources.')
param location string = resourceGroup().location

@description('Short prefix for resource names.')
@maxLength(8)
param namePrefix string = 'an'

@description('Display name (UPN) of the person who administers SQL and Synapse.')
param adminLogin string

@description('Object ID of that person. Also gets Storage Blob Data Reader on the lake (Owner on the subscription does not give data access).')
param adminObjectId string

@description('Your public IP, for the Azure SQL and Synapse firewalls. Empty = no client rule (Synapse serverless is then reachable only from Azure).')
param clientIp string = ''

@description('Allow storage account keys. Off = Entra only. If the Synapse workspace deployment complains, set true for the recording and say so.')
param allowSharedKey bool = false

@secure()
@description('Synapse requires a SQL administrator password even when local authentication is disabled. Random, never used, never shown.')
param synapseSqlPassword string = newGuid()

var suffix = uniqueString(resourceGroup().id)
var storageName = 'st${namePrefix}${suffix}'
var sqlServerName = 'sql-${namePrefix}-${suffix}'
var sqlDbName = 'sourcedb'
var adfName = 'adf-${namePrefix}-${suffix}'
var synapseName = 'syn-${namePrefix}-${suffix}'
var lakeUrl = 'https://${storageName}.dfs.${environment().suffixes.storage}'

var roleBlobContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor
var roleBlobReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'      // Storage Blob Data Reader

// ---------- lake ----------
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    isHnsEnabled: true // hierarchical namespace = ADLS Gen2
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: allowSharedKey
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource lakeContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'lake'
}

resource synapseContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'synapse'
}

// ---------- source database ----------
resource sqlServer 'Microsoft.Sql/servers@2023-08-01' = {
  name: sqlServerName
  location: location
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true
      login: adminLogin
      sid: adminObjectId
      tenantId: tenant().tenantId
      principalType: 'User'
    }
  }
}

// Data Factory's Azure integration runtime connects from Azure addresses: this rule admits any Azure-hosted client.
// Only Entra identities with a database user get in. Production: private endpoint or a self-hosted/VNet integration runtime.
resource allowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01' = {
  parent: sqlServer
  name: 'AllowAllWindowsAzureIps'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource sqlClientRule 'Microsoft.Sql/servers/firewallRules@2023-08-01' = if (!empty(clientIp)) {
  parent: sqlServer
  name: 'recording-laptop'
  properties: { startIpAddress: clientIp, endIpAddress: clientIp }
}

resource sourceDb 'Microsoft.Sql/servers/databases@2023-08-01' = {
  parent: sqlServer
  name: sqlDbName
  location: location
  sku: { name: 'GP_S_Gen5_2', tier: 'GeneralPurpose', family: 'Gen5', capacity: 2 }
  properties: {
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
    requestedBackupStorageRedundancy: 'Local'
  }
}

// ---------- Data Factory ----------
resource adf 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: adfName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

resource adfCanWriteLake 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, adf.id, roleBlobContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleBlobContributor)
    principalId: adf.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource analystCanReadLake 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, adminObjectId, roleBlobReader)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleBlobReader)
    principalId: adminObjectId
    principalType: 'User'
  }
}

resource lsSourceSql 'Microsoft.DataFactory/factories/linkedservices@2018-06-01' = {
  parent: adf
  name: 'ls_source_sql'
  properties: {
    type: 'AzureSqlDatabase'
    typeProperties: {
      server: sqlServer.properties.fullyQualifiedDomainName
      database: sqlDbName
      authenticationType: 'SystemAssignedManagedIdentity'
    }
  }
}

resource lsLake 'Microsoft.DataFactory/factories/linkedservices@2018-06-01' = {
  parent: adf
  name: 'ls_lake'
  properties: {
    type: 'AzureBlobFS'
    typeProperties: { url: lakeUrl }
  }
}

resource dsSourceSql 'Microsoft.DataFactory/factories/datasets@2018-06-01' = {
  parent: adf
  name: 'ds_source_sql'
  properties: loadJsonContent('../adf/dataset-source-sql.json')
  dependsOn: [ lsSourceSql ]
}

resource dsBronze 'Microsoft.DataFactory/factories/datasets@2018-06-01' = {
  parent: adf
  name: 'ds_bronze_parquet'
  properties: loadJsonContent('../adf/dataset-bronze-parquet.json')
  dependsOn: [ lsLake ]
}

resource pipeline 'Microsoft.DataFactory/factories/pipelines@2018-06-01' = {
  parent: adf
  name: 'pl_incremental_purchase_requests'
  properties: loadJsonContent('../adf/pipeline-incremental.json')
  dependsOn: [ dsSourceSql, dsBronze ]
}

// ---------- Synapse workspace (serverless SQL only) ----------
resource synapse 'Microsoft.Synapse/workspaces@2021-06-01' = {
  name: synapseName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    defaultDataLakeStorage: {
      accountUrl: lakeUrl
      filesystem: 'synapse'
    }
    sqlAdministratorLogin: 'sqladminuser'
    sqlAdministratorLoginPassword: synapseSqlPassword
    azureADOnlyAuthentication: true
    publicNetworkAccess: 'Enabled'
  }
  dependsOn: [ synapseContainer ]
}

resource synapseAdmin 'Microsoft.Synapse/workspaces/administrators@2021-06-01' = {
  parent: synapse
  name: 'activeDirectory'
  properties: {
    administratorType: 'ActiveDirectory'
    login: adminLogin
    sid: adminObjectId
    tenantId: tenant().tenantId
  }
}

resource synapseClientRule 'Microsoft.Synapse/workspaces/firewallRules@2021-06-01' = if (!empty(clientIp)) {
  parent: synapse
  name: 'recording-laptop'
  properties: { startIpAddress: clientIp, endIpAddress: clientIp }
}

output storageAccountName string = storage.name
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sourceDatabase string = sqlDbName
output dataFactoryName string = adf.name
output synapseWorkspace string = synapse.name
output synapseServerlessEndpoint string = '${synapse.name}-ondemand.sql.azuresynapse.net'
