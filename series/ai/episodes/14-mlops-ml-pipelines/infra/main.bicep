// DEVLADLOG AI #14: an Azure Machine Learning workspace for the SLA breach pipeline.
//  - The workspace needs a storage account, a key vault and an Application Insights (workspace-based, backed by Log Analytics).
//    The container registry is left out: Azure ML creates one when the first environment is built (see README, not verified here).
//  - Key vault: access policies empty, as in the Azure quickstart template; the workspace's system-assigned identity is granted access by the service.
//  - A compute cluster that scales to ZERO (Learn: set the minimum nodes to 0 to avoid charges when no jobs run).
//  - Optional: a CI identity (user-assigned managed identity or app registration, with a federated credential created elsewhere)
//    gets AzureML Data Scientist on the workspace: everything except creating compute and changing the workspace.
//  - Managed online endpoints are created by the scripts, not by Bicep: their lifecycle belongs to the release, not to the platform.

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-mlops'
param location string = resourceGroup().location
@description('VM size for the training cluster.')
param trainingVmSize string = 'Standard_DS3_v2'
param maxNodes int = 1
@description('Object ID of the CI identity that submits jobs and deploys. Empty = no role assignment.')
param ciPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param ciPrincipalType string = 'ServicePrincipal'

var suffix = take(uniqueString(resourceGroup().id), 6)
var shortSuffix = take(uniqueString(resourceGroup().id), 8)
var azureMlDataScientist = 'f6c7c914-8db3-469d-8ca1-694a8f32e121'

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-law-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-appi-${suffix}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stmlops${shortSuffix}'
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-mlops-${shortSuffix}'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    accessPolicies: []
    enableSoftDelete: true
  }
}

resource workspace 'Microsoft.MachineLearningServices/workspaces@2025-06-01' = {
  name: '${prefix}-mlw-${suffix}'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    friendlyName: 'SLA breach MLOps lab'
    storageAccount: storage.id
    keyVault: vault.id
    applicationInsights: appi.id
  }
}

resource cluster 'Microsoft.MachineLearningServices/workspaces/computes@2025-06-01' = {
  parent: workspace
  name: 'cpu-cluster'
  location: location
  properties: {
    computeType: 'AmlCompute'
    properties: {
      vmSize: trainingVmSize
      vmPriority: 'Dedicated'
      scaleSettings: {
        minNodeCount: 0
        maxNodeCount: maxNodes
        nodeIdleTimeBeforeScaleDown: 'PT2M'
      }
    }
  }
}

resource ciToWorkspace 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(ciPrincipalId)) {
  name: guid(workspace.id, ciPrincipalId, azureMlDataScientist)
  scope: workspace
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureMlDataScientist)
    principalId: ciPrincipalId
    principalType: ciPrincipalType
  }
}

output workspaceName string = workspace.name
output computeName string = cluster.name
