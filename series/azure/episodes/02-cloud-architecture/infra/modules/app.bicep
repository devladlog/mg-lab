// Compute: Linux App Service plan + web app with VNet integration, user-assigned identity and Health check.
param location string
param name string
param tags object
param planSku string
param planCapacity int
param zoneRedundant bool
param appSubnetId string
param workspaceId string
param blobContainerUri string
param keyVaultUri string
param storageId string
param vaultId string

var roles = {
  storageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${name}'
  location: location
  tags: tags
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: last(split(storageId, '/'))
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: last(split(vaultId, '/'))
}

// Least privilege: read blobs, read secrets. Nothing at resource-group scope.
resource blobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, roles.storageBlobDataReader)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataReader)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource secretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, identity.id, roles.keyVaultSecretsUser)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'asp-${name}'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: planSku
    capacity: planCapacity
  }
  properties: {
    reserved: true // Linux
    zoneRedundant: zoneRedundant
  }
}

resource app 'Microsoft.Web/sites@2024-04-01' = {
  name: 'app-${name}-${uniqueString(resourceGroup().id, name)}'
  location: location
  tags: tags
  kind: 'app,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    clientAffinityEnabled: false // stateless: any instance can serve any request
    virtualNetworkSubnetId: appSubnetId
    keyVaultReferenceIdentity: identity.id
    siteConfig: {
      linuxFxVersion: 'DOTNETCORE|10.0'
      alwaysOn: true
      http20Enabled: true
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      healthCheckPath: '/healthz'
      vnetRouteAllEnabled: false // only private (RFC1918) traffic goes into the VNet: enough for private endpoints
      appSettings: [
        { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
        { name: 'Probe__BlobContainerUri', value: blobContainerUri }
        { name: 'Probe__KeyVaultUri', value: keyVaultUri }
      ]
    }
  }
  dependsOn: [blobReader, secretsUser] // the first health ping should already have its roles
}

resource ftpBasicAuth 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: app
  name: 'ftp'
  properties: { allow: false }
}

resource appDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-workspace'
  scope: app
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'AppServiceHTTPLogs', enabled: true }
      { category: 'AppServiceConsoleLogs', enabled: true }
      { category: 'AppServiceAppLogs', enabled: true }
    ]
  }
}

output appName string = app.name
output appHostName string = app.properties.defaultHostName
output identityPrincipalId string = identity.properties.principalId
