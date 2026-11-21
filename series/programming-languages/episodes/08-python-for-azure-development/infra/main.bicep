// Contoso approval packs: one storage account, two private containers, keyless access.
// Deploy into rg-mglab-code-08 (West Europe). Standard_LRS, a few cents for the demo.
targetScope = 'resourceGroup'

@description('Globally unique, 3-24 lowercase letters and digits.')
@minLength(3)
@maxLength(24)
param storageAccountName string

param location string = resourceGroup().location

@description('Object id of the user (or managed identity) that gets blob data access.')
param principalId string

@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

@description('Set to false to record the 403 first; deploy again with true to grant access.')
param assignRole bool = true

// Storage Blob Data Contributor
var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowSharedKeyAccess: false // keyless: Entra ID only
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: account
  name: 'default'
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for name in ['requests', 'packs']: {
    parent: blobService
    name: name
  }
]

resource dataAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (assignRole) {
  scope: account
  name: guid(account.id, principalId, blobDataContributor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
    principalId: principalId
    principalType: principalType
  }
}

output blobEndpoint string = account.properties.primaryEndpoints.blob
