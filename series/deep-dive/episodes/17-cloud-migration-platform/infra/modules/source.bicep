targetScope = 'resourceGroup'

param location string
param addressSpace string
param vmSize string
param adminUsername string

@secure()
param adminPassword string


resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-source'
  location: location
  properties: {
    securityRules: [
      {
        // RDP only from inside the virtual network (the lab reaches it over a bastion or VPN, never the internet)
        name: 'allow-rdp-from-vnet'
        properties: {
          priority: 1000
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '3389'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-source'
  location: location
  properties: {
    addressSpace: { addressPrefixes: [ addressSpace ] }
    subnets: [
      { name: 'snet-app', properties: { addressPrefix: cidrSubnet(addressSpace, 24, 1), networkSecurityGroup: { id: nsg.id } } }
      { name: 'snet-data', properties: { addressPrefix: cidrSubnet(addressSpace, 24, 2), networkSecurityGroup: { id: nsg.id } } }
      { name: 'snet-mgmt', properties: { addressPrefix: cidrSubnet(addressSpace, 24, 3), networkSecurityGroup: { id: nsg.id } } }
    ]
  }
}

resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-con-app01'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: { id: '${vnet.id}/subnets/snet-app' }
          // no public IP address: the VM is private only
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: 'con-app01'
  location: location
  properties: {
    hardwareProfile: { vmSize: vmSize }
    osProfile: {
      computerName: 'con-app01'
      adminUsername: adminUsername
      adminPassword: adminPassword
      windowsConfiguration: { enableAutomaticUpdates: true, provisionVMAgent: true }
    }
    storageProfile: {
      imageReference: { publisher: 'MicrosoftWindowsServer', offer: 'WindowsServer', sku: '2022-datacenter-g2', version: 'latest' }
      osDisk: { createOption: 'FromImage', managedDisk: { storageAccountType: 'StandardSSD_LRS' }, deleteOption: 'Delete' }
    }
    networkProfile: { networkInterfaces: [ { id: nic.id, properties: { deleteOption: 'Delete' } } ] }
  }
}

output vmName string = vm.name
output vnetName string = vnet.name
