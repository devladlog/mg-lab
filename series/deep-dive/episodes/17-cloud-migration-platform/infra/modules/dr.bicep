targetScope = 'resourceGroup'

param location string
param addressSpace string

resource vault 'Microsoft.RecoveryServices/vaults@2024-04-01' = {
  name: 'rsv-mglab-dr'
  location: location
  sku: { name: 'RS0', tier: 'Standard' }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-target'
  location: location
  properties: {
    addressSpace: { addressPrefixes: [ addressSpace ] }
    subnets: [
      { name: 'snet-app', properties: { addressPrefix: cidrSubnet(addressSpace, 24, 1) } }
      { name: 'snet-data', properties: { addressPrefix: cidrSubnet(addressSpace, 24, 2) } }
      { name: 'snet-mgmt', properties: { addressPrefix: cidrSubnet(addressSpace, 24, 3) } }
    ]
  }
}

output vaultName string = vault.name
output vnetName string = vnet.name
