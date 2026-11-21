// Episode 8, comparison: the same image on the smallest real AKS cluster we could justify for a recording.
//  - Free tier control plane (no uptime SLA, recommended for fewer than 10 nodes; dev/test only)
//  - ONE system node, Standard_D4as_v5 (4 vCPU / 16 GiB): Learn requires at least 4 vCPUs and 4 GB for system
//    pools and no B-series. Learn also says a production cluster with a single system pool must have at least two
//    nodes (three recommended): one node is a lab-only shortcut for a recording window of at most two hours,
//    then the cluster is deleted.
//  - Managed 64 GB OS disk, set explicitly so its size and price are known
//  - The kubelet identity gets AcrPull on episode 8's registry (deployed by aca.bicep in the same group)
// Pay-as-you-go while it exists: about 0.23 EUR per hour (see demo.md). Delete it right after the AKS scenes.

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@minLength(3)
@maxLength(10)
param prefix string = 'orders'

@description('Name of the registry created by aca.bicep (output acrName).')
param acrName string

param nodeVmSize string = 'Standard_D4as_v5'

@minValue(1)
@maxValue(3)
param nodeCount int = 1

param tags object = {
  workload: 'contoso-orders'
  environment: 'lab'
}

var acrPullRole = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acr 'Microsoft.ContainerRegistry/registries@2025-04-01' existing = {
  name: acrName
}

resource aks 'Microsoft.ContainerService/managedClusters@2025-05-01' = {
  name: 'aks-${prefix}-lab'
  location: location
  tags: tags
  sku: { name: 'Base', tier: 'Free' }
  identity: { type: 'SystemAssigned' }
  properties: {
    dnsPrefix: 'aks-${prefix}-lab'
    enableRBAC: true
    agentPoolProfiles: [
      {
        name: 'system'
        mode: 'System'
        type: 'VirtualMachineScaleSets'
        count: nodeCount
        vmSize: nodeVmSize
        osType: 'Linux'
        osSKU: 'AzureLinux'
        osDiskType: 'Managed'
        osDiskSizeGB: 64
      }
    ]
    networkProfile: {
      networkPlugin: 'azure'
      networkPluginMode: 'overlay'
      loadBalancerSku: 'standard'
    }
  }
}

resource kubeletAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, aks.id, acrPullRole)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRole)
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

output clusterName string = aks.name
output nodeResourceGroup string = aks.properties.nodeResourceGroup
