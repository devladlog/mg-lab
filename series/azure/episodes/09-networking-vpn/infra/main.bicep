// DEVLADLOG Azure #9: hub-and-spoke with a point-to-site VPN. One VPN gateway in the hub, one spoke with a private VM
// that has no public IP and only answers to the VPN client pool. Address ranges come from src/netplan/plan.json
// (infra/deploy.sh runs netplan.py first); the certificate data and the SSH key are added by deploy.sh.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param tags object = {
  workload: 'contoso-orders'
  environment: 'lab'
}

param hubAddressSpace string
param gatewaySubnetPrefix string
param spokeAddressSpace string
param workloadSubnetPrefix string
@description('Static private IP of the VM: the first address Azure allows in the subnet (.4).')
param workloadVmIp string
@description('Address pool the VPN gateway hands to connected clients. Must not overlap any VNet or on-premises range.')
param p2sPoolPrefix string

@description('Base64 DER of the P2S root certificate, no header lines (infra/certs.sh writes it).')
param p2sRootCertData string
@description('SSH public key for the VM admin user (deploy.sh generates a throwaway pair).')
param sshPublicKey string

param vmSize string = 'Standard_B1s'
param adminUsername string = 'azureadmin'

var cloudInit = loadFileAsBase64('cloud-init.yaml')

resource hub 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-hub'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [hubAddressSpace] }
    subnets: [
      {
        name: 'GatewaySubnet' // the name is mandatory; never put anything else in this subnet
        properties: { addressPrefix: gatewaySubnetPrefix }
      }
    ]
  }
}

resource nsgWorkload 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-workload'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'allow-orders-from-vpn-pool'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: p2sPoolPrefix
          sourcePortRange: '*'
          destinationAddressPrefix: workloadVmIp
          destinationPortRange: '8080'
        }
      }
      {
        name: 'deny-all-inbound'
        properties: {
          priority: 4000
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource spoke 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-orders'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [spokeAddressSpace] }
    subnets: [
      {
        name: 'workload'
        properties: {
          addressPrefix: workloadSubnetPrefix
          networkSecurityGroup: { id: nsgWorkload.id }
          defaultOutboundAccess: false // private subnet: no implicit internet egress
        }
      }
    ]
  }
}

resource gatewayIp 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-vpngw'
  location: location
  tags: tags
  sku: { name: 'Standard' }
  zones: ['1', '2', '3']
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource gateway 'Microsoft.Network/virtualNetworkGateways@2024-05-01' = {
  name: 'vgw-hub'
  location: location
  tags: tags
  properties: {
    gatewayType: 'Vpn'
    vpnType: 'RouteBased'
    vpnGatewayGeneration: 'Generation1'
    sku: { name: 'VpnGw1AZ', tier: 'VpnGw1AZ' } // new gateways must use an AZ SKU and a Standard public IP
    enableBgp: false
    activeActive: false
    ipConfigurations: [
      {
        name: 'default'
        properties: {
          publicIPAddress: { id: gatewayIp.id }
          subnet: { id: '${hub.id}/subnets/GatewaySubnet' }
        }
      }
    ]
    vpnClientConfiguration: {
      vpnClientAddressPool: { addressPrefixes: [p2sPoolPrefix] }
      vpnClientProtocols: ['IkeV2', 'OpenVPN']
      vpnAuthenticationTypes: ['Certificate']
      vpnClientRootCertificates: [
        {
          name: 'contoso-p2s-root'
          properties: { publicCertData: p2sRootCertData }
        }
      ]
    }
  }
}

// Peering is directional: both directions are needed. Gateway transit on the hub side, remote gateway on the spoke side.
resource hubToSpoke 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-05-01' = {
  parent: hub
  name: 'hub-to-orders'
  properties: {
    remoteVirtualNetwork: { id: spoke.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: true
    useRemoteGateways: false
  }
  dependsOn: [gateway]
}

resource spokeToHub 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-05-01' = {
  parent: spoke
  name: 'orders-to-hub'
  properties: {
    remoteVirtualNetwork: { id: hub.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
    allowGatewayTransit: false
    useRemoteGateways: true
  }
  dependsOn: [gateway, hubToSpoke]
}

resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-orders-vm'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Static'
          privateIPAddress: workloadVmIp
          subnet: { id: '${spoke.id}/subnets/workload' }
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: 'vm-orders-int'
  location: location
  tags: tags
  properties: {
    hardwareProfile: { vmSize: vmSize }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: { storageAccountType: 'StandardSSD_LRS' }
        diskSizeGB: 30
        deleteOption: 'Delete'
      }
    }
    osProfile: {
      computerName: 'vm-orders-int'
      adminUsername: adminUsername
      customData: cloudInit
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: sshPublicKey
            }
          ]
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        { id: nic.id, properties: { deleteOption: 'Delete' } }
      ]
    }
  }
}

output gatewayName string = gateway.name
output gatewayPublicIpName string = gatewayIp.name
output vmName string = vm.name
output vmPrivateIp string = workloadVmIp
