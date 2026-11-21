// Data tier: storage + Key Vault, both reachable ONLY through private endpoints, both logging to the workspace.
param location string
param name string
param tags object
param storageSku string
param keyVaultPurgeProtection bool
param peSubnetId string
param blobZoneId string
param vaultZoneId string
param workspaceId string

@secure()
param probeSecretValue string

var token = uniqueString(resourceGroup().id, name)

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('st${replace(name, '-', '')}${token}', 24)
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: storageSku }
  properties: {
    publicNetworkAccess: 'Disabled'
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    networkAcls: { defaultAction: 'Deny', bypass: 'None' }
  }

  resource blobs 'blobServices' = {
    name: 'default'
    properties: {
      deleteRetentionPolicy: { enabled: true, days: 7 }
      containerDeleteRetentionPolicy: { enabled: true, days: 7 }
    }
    resource probe 'containers' = { name: 'probe' }
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take('kv-${name}-${token}', 24)
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: keyVaultPurgeProtection ? true : null // can't be set to false once enabled
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny', bypass: 'None' }
  }

  resource probeSecret 'secrets' = {
    name: 'probe-secret'
    tags: tags
    properties: { value: probeSecretValue, contentType: 'text/plain' }
  }
}

resource blobEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${storage.name}-blob'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      { name: 'blob', properties: { privateLinkServiceId: storage.id, groupIds: ['blob'] } }
    ]
  }
  resource dns 'privateDnsZoneGroups' = {
    name: 'default'
    properties: { privateDnsZoneConfigs: [{ name: 'blob', properties: { privateDnsZoneId: blobZoneId } }] }
  }
}

resource vaultEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${vault.name}-vault'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      { name: 'vault', properties: { privateLinkServiceId: vault.id, groupIds: ['vault'] } }
    ]
  }
  resource dns 'privateDnsZoneGroups' = {
    name: 'default'
    properties: { privateDnsZoneConfigs: [{ name: 'vault', properties: { privateDnsZoneId: vaultZoneId } }] }
  }
}

resource blobDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-workspace'
  scope: storage::blobs
  properties: {
    workspaceId: workspaceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
  }
}

resource vaultDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-workspace'
  scope: vault
  properties: {
    workspaceId: workspaceId
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
  }
}

output storageId string = storage.id
output vaultId string = vault.id
output blobContainerUri string = '${storage.properties.primaryEndpoints.blob}probe'
output keyVaultUri string = vault.properties.vaultUri
