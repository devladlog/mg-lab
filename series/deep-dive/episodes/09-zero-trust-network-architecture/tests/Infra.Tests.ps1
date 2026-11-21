#requires -Modules Pester
# Contract tests on the COMPILED Bicep (real `bicep build`): the Zero Trust properties must be in the template.
BeforeAll {
    $root = Split-Path $PSScriptRoot -Parent
    $script:Arm = (& bicep build (Join-Path $root 'infra/main.bicep') --stdout) | ConvertFrom-Json -Depth 50
    function script:Res([string]$type) { @($script:Arm.resources | Where-Object type -eq $type) }
}

Describe 'Key Vault' {
    BeforeAll { $script:Kv = (Res 'Microsoft.KeyVault/vaults')[0] }
    It 'has public network access disabled and the firewall on deny' {
        $script:Kv.properties.publicNetworkAccess | Should -Be 'Disabled'
        $script:Kv.properties.networkAcls.defaultAction | Should -Be 'Deny'
    }
    It 'uses Azure RBAC, not access policies' { $script:Kv.properties.enableRbacAuthorization | Should -BeTrue }
    It 'keeps soft delete at the 7 day minimum and does not turn on purge protection (tear-down must be able to purge)' {
        $script:Kv.properties.softDeleteRetentionInDays | Should -Be 7
        $script:Kv.properties.PSObject.Properties.Name | Should -Not -Contain 'enablePurgeProtection'
    }
}

Describe 'Private endpoint' {
    It 'targets the vault sub-resource and the documented private DNS zone' {
        $pe = (Res 'Microsoft.Network/privateEndpoints')[0]
        $pe.properties.privateLinkServiceConnections[0].properties.groupIds | Should -Be @('vault')
        (Res 'Microsoft.Network/privateDnsZones').name | Should -Be 'privatelink.vaultcore.azure.net'
    }
    It 'links the zone to the network without auto-registration' {
        $l = Res 'Microsoft.Network/privateDnsZones/virtualNetworkLinks'
        $l.Count | Should -Be 1
        $l[0].properties.registrationEnabled | Should -BeFalse
    }
    It 'registers the endpoint in the zone through a DNS zone group' {
        (Res 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups').Count | Should -Be 1
    }
}

Describe 'Network' {
    It 'denies all inbound at priority 4096 and the internet outbound' {
        $rules = (Res 'Microsoft.Network/networkSecurityGroups')[0].properties.securityRules
        $in = $rules | Where-Object { $_.properties.direction -eq 'Inbound' }
        @($in).Count | Should -Be 1
        $in[0].properties.access | Should -Be 'Deny'
        $in[0].properties.priority | Should -Be 4096
        $out = $rules | Where-Object { $_.properties.direction -eq 'Outbound' }
        $out[0].properties.destinationAddressPrefix | Should -Be 'Internet'
        $out[0].properties.access | Should -Be 'Deny'
    }
    It 'creates no public IP address' { (Res 'Microsoft.Network/publicIPAddresses').Count | Should -Be 0 }
    It 'uses private subnets and does not overlap the Hyper-V lab network 10.50.0.0/24' {
        $vnet = (Res 'Microsoft.Network/virtualNetworks')[0]
        $vnet.properties.addressSpace.addressPrefixes | Should -Be @('10.60.0.0/24')
        $vnet.properties.subnets | ForEach-Object { $_.properties.defaultOutboundAccess | Should -BeFalse }
    }
}

Describe 'Workload VM' {
    It 'logs in with an SSH key only and has a system-assigned identity' {
        $vm = (Res 'Microsoft.Compute/virtualMachines')[0]
        $vm.properties.osProfile.linuxConfiguration.disablePasswordAuthentication | Should -BeTrue
        $vm.identity.type | Should -Be 'SystemAssigned'
    }
    It 'gets exactly one role, Key Vault Secrets User, scoped to the vault' {
        $ra = Res 'Microsoft.Authorization/roleAssignments'
        $ra.Count | Should -Be 1
        $script:Arm.variables.keyVaultSecretsUser | Should -Be '4633458b-17de-408a-b874-0445c86b69e6'
        $ra[0].properties.roleDefinitionId | Should -Match 'keyVaultSecretsUser'
        $ra[0].scope | Should -Match 'Microsoft.KeyVault/vaults'
    }
}

Describe 'Scripts' {
    It 'vm-check.sh is valid bash' {
        & bash -n (Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/vm-check.sh')
        $LASTEXITCODE | Should -Be 0
    }
    It 'Test-PrivateAccess.ps1 -PrintOnly prints the two az commands and runs nothing' {
        $out = & (Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/Test-PrivateAccess.ps1') -ResourceGroup rg -VaultName kv1 -VmName vm1 -PrintOnly
        $out[0] | Should -Match 'az keyvault secret show --vault-name kv1'
        $out[1] | Should -Match 'az vm run-command invoke -g rg -n vm1 --command-id RunShellScript'
    }
}
