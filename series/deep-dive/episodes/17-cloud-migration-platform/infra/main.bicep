// Landing zone for the migration demo: a source network with one private-only test VM in West Europe, and a disaster-recovery
// resource group in North Europe with the Recovery Services vault and a target network.
// Learn (Site Recovery, Azure to Azure): the vault and its resource group must be in a region other than the source VMs'.
// The source virtual network (10.60.0.0/16) and the target (10.61.0.0/16) do not overlap each other or the lab's 10.50.0.0/24.
targetScope = 'subscription'

@description('Region of the source VM and network.')
param sourceLocation string = 'westeurope'

@description('Region of the vault and the target network. Must differ from sourceLocation.')
param drLocation string = 'northeurope'

@description('Episode number, used in the resource group names (rg-mglab-deep-dive-<ep>).')
param episode string = '17'

param sourceAddressSpace string = '10.60.0.0/16'
param drAddressSpace string = '10.61.0.0/16'

@description('Size of the test VM. Standard_D2s_v5 has 2 vCPU and 8 GiB (Learn, Dsv5 sizes).')
param vmSize string = 'Standard_D2s_v5'

param adminUsername string = 'labadmin'

@secure()
@description('Local administrator password of the test VM. Supplied at deployment time, never stored in a file.')
param adminPassword string

var sourceRgName = 'rg-mglab-deep-dive-${episode}'
var drRgName = 'rg-mglab-deep-dive-${episode}-dr'

resource sourceRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: sourceRgName
  location: sourceLocation
}

resource drRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: drRgName
  location: drLocation
}

module source 'modules/source.bicep' = {
  scope: sourceRg
  name: 'source'
  params: {
    location: sourceLocation
    addressSpace: sourceAddressSpace
    vmSize: vmSize
    adminUsername: adminUsername
    adminPassword: adminPassword
  }
}

module dr 'modules/dr.bicep' = {
  scope: drRg
  name: 'dr'
  params: {
    location: drLocation
    addressSpace: drAddressSpace
  }
}

output sourceResourceGroup string = sourceRg.name
output drResourceGroup string = drRg.name
output vmName string = source.outputs.vmName
output vaultName string = dr.outputs.vaultName
output sourceVnetName string = source.outputs.vnetName
output targetVnetName string = dr.outputs.vnetName
