// Reference workload for DEVLADLOG Azure #2: web app -> private endpoints -> storage + Key Vault.
// One template, two environment profiles. The shape is identical; only SKUs and resilience settings change.
targetScope = 'resourceGroup'

@allowed(['lab', 'prod'])
param environment string

param location string = resourceGroup().location

@minLength(3)
@maxLength(12)
param workload string = 'contoso'

@description('Required on every resource; the governance template denies resources without it.')
param tags object = {
  workload: workload
  environment: environment
  owner: 'platform-team'
}

@secure()
param probeSecretValue string = newGuid()

// Architecture decisions per environment, in one place (and pinned by tests/guardrails).
var profiles = {
  lab: {
    planSku: 'B1'
    planCapacity: 1
    zoneRedundant: false
    storageSku: 'Standard_LRS'
    keyVaultPurgeProtection: false
    logRetentionInDays: 30
  }
  prod: {
    planSku: 'P1v3'
    planCapacity: 2 // zone redundancy needs at least two instances
    zoneRedundant: true
    storageSku: 'Standard_ZRS'
    keyVaultPurgeProtection: true
    logRetentionInDays: 90
  }
}
var profile = profiles[environment]
var name = '${workload}-${environment}'

module network 'modules/network.bicep' = {
  name: 'network'
  params: { location: location, name: name, tags: tags }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: { location: location, name: name, tags: tags, retentionInDays: profile.logRetentionInDays }
}

module data 'modules/data.bicep' = {
  name: 'data'
  params: {
    location: location
    name: name
    tags: tags
    storageSku: profile.storageSku
    keyVaultPurgeProtection: profile.keyVaultPurgeProtection
    peSubnetId: network.outputs.peSubnetId
    blobZoneId: network.outputs.blobZoneId
    vaultZoneId: network.outputs.vaultZoneId
    workspaceId: monitoring.outputs.workspaceId
    probeSecretValue: probeSecretValue
  }
}

module app 'modules/app.bicep' = {
  name: 'app'
  params: {
    location: location
    name: name
    tags: tags
    planSku: profile.planSku
    planCapacity: profile.planCapacity
    zoneRedundant: profile.zoneRedundant
    appSubnetId: network.outputs.appSubnetId
    workspaceId: monitoring.outputs.workspaceId
    blobContainerUri: data.outputs.blobContainerUri
    keyVaultUri: data.outputs.keyVaultUri
    storageId: data.outputs.storageId
    vaultId: data.outputs.vaultId
  }
}

output appName string = app.outputs.appName
output appUrl string = 'https://${app.outputs.appHostName}'
output healthUrl string = 'https://${app.outputs.appHostName}/healthz'
