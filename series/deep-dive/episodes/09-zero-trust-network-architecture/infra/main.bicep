// DEVLADLOG Deep Dive #9: the network half of Contoso's Zero Trust lab.
// One Key Vault with public access OFF, reachable only through a private endpoint; one small VM inside the
// network with a managed identity, no public IP, no inbound rule and no route to the internet.
targetScope = 'resourceGroup'

@description('Region. West Europe for the lab.')
param location string = resourceGroup().location

@description('Short prefix for names.')
@minLength(3)
@maxLength(8)
param namePrefix string = 'mgl09'

@description('SSH public key for the VM admin user (key only, password login is off). Generate a throwaway pair for the recording.')
param adminPublicKey string

@description('Admin user name of the VM (SSH key only).')
param adminUsername string = 'ztadmin'

@description('VM size. Check availability in the region first: az vm list-skus -l westeurope --size Standard_B1s -o table')
param vmSize string = 'Standard_B1s'

var token = take(uniqueString(resourceGroup().id), 6)
var vaultName = 'kv-${namePrefix}-${token}'
var vnetName = 'vnet-${namePrefix}'
var keyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6' // built-in role: Key Vault Secrets User

// ---- Network: deny by default, say it out loud --------------------------------------------------------
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-zerotrust-workloads'
  location: location
  properties: {
    securityRules: [
      {
        name: 'deny-all-inbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '*'
        }
      }
      {
        name: 'deny-internet-outbound'
        properties: {
          priority: 4000
          direction: 'Outbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: '*'
          sourcePortRange: '*'
          destinationAddressPrefix: 'Internet'
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: { addressPrefixes: ['10.60.0.0/24'] } // not 10.50.0.0/24: that is the Hyper-V lab
    subnets: [
      {
        name: 'snet-workloads'
        properties: {
          addressPrefix: '10.60.0.0/26'
          networkSecurityGroup: { id: nsg.id }
          defaultOutboundAccess: false // private subnet: no implicit internet egress
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: '10.60.0.64/27'
          defaultOutboundAccess: false
        }
      }
    ]
  }
}

// ---- Key Vault: no public network, RBAC only -----------------------------------------------------------
resource vault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: vaultName
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny', bypass: 'None' }
    enableSoftDelete: true
    softDeleteRetentionInDays: 7 // minimum; no purge protection in the lab, so tear-down can purge
  }
}

resource demoSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = {
  parent: vault
  name: 'demo-secret'
  properties: { value: 'contoso-zero-trust-lab' } // not a real secret
}

// ---- Private endpoint + private DNS --------------------------------------------------------------------
resource dnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
}

resource dnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: dnsZone
  name: 'link-${vnetName}'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

resource pe 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-keyvault-zerotrust'
  location: location
  properties: {
    subnet: { id: '${vnet.id}/subnets/snet-private-endpoints' }
    privateLinkServiceConnections: [
      {
        name: 'kv'
        properties: {
          privateLinkServiceId: vault.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource peDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: pe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'vaultcore', properties: { privateDnsZoneId: dnsZone.id } }
    ]
  }
}

// ---- The workload: a VM with an identity and nothing else ----------------------------------------------
resource nic 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-${namePrefix}-workload'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: { id: '${vnet.id}/subnets/snet-workloads' }
          privateIPAllocationMethod: 'Dynamic' // no publicIPAddress on purpose
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: 'vm-${namePrefix}-workload'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    hardwareProfile: { vmSize: vmSize }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: { createOption: 'FromImage', managedDisk: { storageAccountType: 'StandardSSD_LRS' }, deleteOption: 'Delete' }
    }
    osProfile: {
      computerName: 'workload01'
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: { publicKeys: [{ path: '/home/${adminUsername}/.ssh/authorized_keys', keyData: adminPublicKey }] }
      }
    }
    networkProfile: { networkInterfaces: [{ id: nic.id, properties: { deleteOption: 'Delete' } }] }
  }
}

// The VM may read secrets in this one vault. Nothing wider.
resource vmReadsSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, vm.id, keyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUser)
    principalId: vm.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output vaultName string = vault.name
output vaultUri string = vault.properties.vaultUri
output vmName string = vm.name
