// Episode 7: the right store for each kind of data, with no secrets anywhere.
//  - Orders (relational, transactional): Azure SQL Database, free tier (General Purpose serverless),
//    Microsoft Entra-only authentication: SQL logins and passwords are switched off at the server.
//  - Invoices (documents, written once, read rarely, kept for years): Blob Storage with shared keys
//    disabled, a lifecycle policy (Hot -> Cool -> Cold -> delete) and soft delete.
// Nothing in this template has a password or key parameter.

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@minLength(3)
@maxLength(10)
param prefix string = 'orders'

@description('Object ID of the Entra user (or group) that becomes the SQL Entra admin and gets blob data access.')
param adminObjectId string

@description('UPN or display name shown as the SQL Entra admin login.')
param adminLogin string

@description('User for a person, Group for an Entra group.')
@allowed(['User', 'Group'])
param adminPrincipalType string = 'User'

@description('Public IPv4 of the machine that runs the API during the demo (one address, not a range).')
param clientIp string

@description('Invoices move to Cool after this many days (Cool has a 30-day minimum before an early-deletion charge).')
param coolAfterDays int = 30

@description('...and to Cold after this many days (Cold has a 90-day minimum).')
param coldAfterDays int = 90

@description('Invoices are deleted after this many days. Ten years is an example: use your own retention rule.')
param deleteAfterDays int = 3650

param tags object = {
  workload: 'contoso-orders'
  environment: 'lab'
}

var token = toLower(uniqueString(subscription().id, resourceGroup().id, prefix))
var storageName = take('st${prefix}${token}', 24)
var sqlServerName = 'sql-${prefix}-${token}'
var databaseName = 'sqldb-${prefix}'
var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // includes generateUserDelegationKey

// ---------- Blob Storage: invoices ----------

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot'
    allowSharedKeyAccess: false // no account keys, no account/service SAS: Entra ID and user delegation SAS only
    defaultToOAuthAuthentication: true
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled' // the lab API runs on a laptop; episode 2 shows the private-endpoint version
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
    containerDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource invoices 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'invoices'
  properties: { publicAccess: 'None' }
}

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'invoices-age-out'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['invoices/']
            }
            actions: {
              baseBlob: {
                tierToCool: { daysAfterCreationGreaterThan: coolAfterDays }
                tierToCold: { daysAfterCreationGreaterThan: coldAfterDays }
                delete: { daysAfterCreationGreaterThan: deleteAfterDays }
              }
            }
          }
        }
      ]
    }
  }
}

resource adminBlobAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, adminObjectId, blobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
    principalId: adminObjectId
    principalType: adminPrincipalType
  }
}

// ---------- Azure SQL Database: orders ----------

resource sqlServer 'Microsoft.Sql/servers@2023-08-01' = {
  name: sqlServerName
  location: location
  tags: tags
  properties: {
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true // no SQL authentication at all, so no administratorLogin/password
      login: adminLogin
      sid: adminObjectId
      principalType: adminPrincipalType
      tenantId: tenant().tenantId
    }
  }
}

resource clientRule 'Microsoft.Sql/servers/firewallRules@2023-08-01' = {
  parent: sqlServer
  name: 'demo-client'
  properties: {
    startIpAddress: clientIp
    endIpAddress: clientIp
  }
}

resource database 'Microsoft.Sql/servers/databases@2023-08-01' = {
  parent: sqlServer
  name: databaseName
  location: location
  tags: tags
  sku: {
    name: 'GP_S_Gen5' // General Purpose, serverless
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 2
  }
  properties: {
    createMode: 'Default'
    maxSizeBytes: 34359738368 // 32 GB, the free tier's data allowance
    requestedBackupStorageRedundancy: 'Local'
    useFreeLimit: true // free tier: 100,000 vCore seconds + 32 GB data + 32 GB backup per month
    freeLimitExhaustionBehavior: 'AutoPause' // never 'BillOverUsage' in the lab
  }
}

output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output databaseName string = database.name
output blobServiceUri string = storage.properties.primaryEndpoints.blob
output storageAccountName string = storage.name
