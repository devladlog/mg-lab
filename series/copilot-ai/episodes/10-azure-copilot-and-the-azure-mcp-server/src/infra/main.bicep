// DEVLADLOG Copilot & AI #10: the few resources Azure Copilot and the Azure MCP Server are asked about.
// Deploy into the resource group rg-mglab-copilot-10 (West Europe). Everything here is the cheapest SKU and is deleted in tear-down.
targetScope = 'resourceGroup'

@description('Azure region. The resource group is created in West Europe, so the default follows it.')
param location string = resourceGroup().location

@description('Object id of the user who gets the Reader role on this resource group (the "can only read" take). Leave empty to skip.')
param readerObjectId string = ''

var tags = {
  purpose: 'mglab-copilot-ai-10'
  disposable: 'true'
}

// Storage names: 3-24 lowercase letters and digits, globally unique. 'stmglab10' + 13 characters = 22.
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stmglab10${uniqueString(resourceGroup().id)}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    accessTier: 'Hot'
  }
}

// A CanNotDelete lock: Learn says Azure Copilot respects resource locks. Remove it before deleting the resource group.
resource storageLock 'Microsoft.Authorization/locks@2020-05-01' = {
  name: 'lock-do-not-delete'
  scope: storage
  properties: {
    level: 'CanNotDelete'
    notes: 'Demo: Azure Copilot and the Azure MCP Server must not be able to delete this account.'
  }
}

// Key names: 3-24 characters. 'kv-mglab10-' + 8 = 19. Azure RBAC authorization, no purge protection (so tear-down can purge it).
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-mglab10-${take(uniqueString(resourceGroup().id), 8)}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// A secret that exists only to show the confirmation prompt (elicitation) when a tool reads a secret. Not a real secret.
resource demoSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'demo-secret'
  properties: {
    value: 'this-is-not-a-real-secret'
  }
}

// Reader (acdd72a7-3385-48ef-bd42-f606fba81ae7, Learn: Azure built-in roles) for the "read only" user.
var readerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
resource readerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(readerObjectId)) {
  name: guid(resourceGroup().id, readerObjectId, readerRoleId)
  properties: {
    roleDefinitionId: readerRoleId
    principalId: readerObjectId
    principalType: 'User'
  }
}

output storageAccountName string = storage.name
output keyVaultName string = vault.name
