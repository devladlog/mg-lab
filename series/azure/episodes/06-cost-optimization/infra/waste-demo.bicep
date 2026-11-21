// Deliberate waste for the demo, the kind that is left behind when a project ends:
// a static public IP attached to nothing (and missing the workload tag), and an App Service plan
// whose apps were deleted. deploy-waste-demo.sh adds two unattached disks with the Azure CLI.
// Cost while it exists: about 0.02 EUR per hour in Sweden Central. Delete it the same day.

targetScope = 'resourceGroup'

param location string = resourceGroup().location

resource forgottenIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-contoso-forgotten'
  location: location
  // no tags on purpose: the untagged query should find it
  sku: { name: 'Standard', tier: 'Regional' }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
}

resource leftoverPlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-contoso-leftover'
  location: location
  tags: { workload: 'contoso-waste', environment: 'lab' }
  kind: 'linux'
  sku: { name: 'B1', capacity: 1 }
  properties: { reserved: true }
}

output publicIpId string = forgottenIp.id
output planId string = leftoverPlan.id
