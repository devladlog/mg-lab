// Network: one VNet, two subnets (app integration + private endpoints), NSGs, private DNS zones.
param location string
param name string
param tags object

// Private DNS zones for the private endpoints. The blob suffix comes from environment() so the same
// template works in other clouds (the linter rejects a hardcoded core.windows.net).
var privateDnsZoneNames = [
  'privatelink.blob.${environment().suffixes.storage}'
  'privatelink.vaultcore.azure.net'
]

resource nsgApp 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-${name}-app'
  location: location
  tags: tags
  properties: {
    securityRules: [
      // No SSH or RDP from this subnet to the rest of the VNet (lateral movement)
      {
        name: 'deny-ssh-rdp-to-vnet'
        properties: {
          priority: 4000
          direction: 'Outbound'
          access: 'Deny'
          protocol: 'Tcp'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRanges: ['22', '3389']
        }
      }
    ]
  }
}

resource nsgPe 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-${name}-pe'
  location: location
  tags: tags
  properties: {
    securityRules: [
      // No SSH or RDP from this subnet to the rest of the VNet (lateral movement)
      {
        name: 'deny-ssh-rdp-to-vnet'
        properties: {
          priority: 4000
          direction: 'Outbound'
          access: 'Deny'
          protocol: 'Tcp'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'VirtualNetwork'
          destinationPortRanges: ['22', '3389']
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${name}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.50.0.0/24'] }
    subnets: [
      {
        name: 'snet-app' // App Service VNet integration: empty, delegated, /26 recommended
        properties: {
          addressPrefix: '10.50.0.0/26'
          defaultOutboundAccess: false
          networkSecurityGroup: { id: nsgApp.id }
          delegations: [
            {
              name: 'webapp'
              properties: { serviceName: 'Microsoft.Web/serverFarms' }
            }
          ]
        }
      }
      {
        name: 'snet-pe' // private endpoints for storage and Key Vault
        properties: {
          addressPrefix: '10.50.0.64/26'
          defaultOutboundAccess: false
          networkSecurityGroup: { id: nsgPe.id }
        }
      }
    ]
  }
}

resource zones 'Microsoft.Network/privateDnsZones@2024-06-01' = [
  for zone in privateDnsZoneNames: {
    name: zone
    location: 'global'
    tags: tags
  }
]

resource links 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for (zone, i) in privateDnsZoneNames: {
    parent: zones[i]
    name: 'link-${vnet.name}'
    location: 'global'
    tags: tags
    properties: {
      registrationEnabled: false
      virtualNetwork: { id: vnet.id }
    }
  }
]

output appSubnetId string = vnet.properties.subnets[0].id
output peSubnetId string = vnet.properties.subnets[1].id
output blobZoneId string = zones[0].id
output vaultZoneId string = zones[1].id
