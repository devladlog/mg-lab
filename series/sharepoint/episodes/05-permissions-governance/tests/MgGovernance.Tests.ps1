#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# The tenant tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong
# parameter name or type fails the test). They are skipped when PnP.PowerShell isn't installed.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
}

BeforeAll {
    $src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgGovernance.psm1') -Force
    $script:policy = Import-MgJson -Path (Join-Path $src 'governance' 'purchasing.policy.json')
    $script:bad = Import-MgJson -Path (Join-Path $src 'bad' 'loose.policy.json')
    $script:drifted = Import-MgJson -Path (Join-Path $src 'fixtures' 'drifted.snapshot.json')
    $script:labelId = '00000000-0000-0000-0000-00000000c0f1'

    function Rules($f) { @($f | ForEach-Object Rule) }
    function Copy-Json($o) { $o | ConvertTo-Json -Depth 30 | ConvertFrom-Json -Depth 30 }
    function Audit($s, $p = $script:policy) { @(Test-MgPermissionSnapshot -Snapshot $s -Policy $p -SensitivityLabelId $labelId) }
    function Principal([string]$Title, [string]$Type = 'User', [string[]]$Roles = @('Read'), [string]$Login) {
        [pscustomobject]@{ title = $Title; loginName = $(if ($Login) { $Login } else { "i:0#.f|membership|$($Title.Replace(' ', '.').ToLower())@contoso.com" }); principalType = $Type; roles = $Roles }
    }

    # Applies a remediation plan to a snapshot the way the PnP calls would change the site (offline model).
    function Invoke-PlanOnSnapshot($Snapshot, $Plan) {
        $s = Copy-Json $Snapshot
        foreach ($f in @($Plan | ForEach-Object Fix)) {
            switch ($f.Action) {
                'SetSite' {
                    if ($f.PSObject.Properties['SharingCapability']) { $s.sharingCapability = $f.SharingCapability }
                    if ($f.PSObject.Properties['DefaultSharingLinkType']) { $s.defaultSharingLinkType = $f.DefaultSharingLinkType }
                    if ($f.PSObject.Properties['DefaultLinkPermission']) { $s.defaultLinkPermission = $f.DefaultLinkPermission }
                    if ($f.PSObject.Properties['SensitivityLabel']) { $s.sensitivityLabel = $f.SensitivityLabel }
                }
                'RemoveSharingLink' { $s.sharingLinks = @($s.sharingLinks | Where-Object id -ne $f.LinkId) }
                'ResetItemInheritance' { $s.scopes = @($s.scopes | Where-Object { -not ($_.kind -eq 'Item' -and $_.id -eq $f.ItemId) }) }
                'ResetListInheritance' { ($s.scopes | Where-Object { $_.kind -eq 'List' -and $_.title -eq $f.List }) | ForEach-Object { $_.unique = $false; $_.assignments = @() } }
                'RemoveGroupMember' { ($s.groups | Where-Object title -eq $f.Group) | ForEach-Object { $_.members = @($_.members | Where-Object loginName -ne $f.LoginName) } }
                'RemoveGrant' {
                    $scope = switch ($f.Kind) {
                        'Web' { $s.scopes | Where-Object kind -eq 'Web' }
                        'List' { $s.scopes | Where-Object { $_.kind -eq 'List' -and $_.title -eq $f.List } }
                        'Item' { $s.scopes | Where-Object { $_.kind -eq 'Item' -and $_.id -eq $f.ItemId } }
                    }
                    $who = if ($f.PSObject.Properties['Group']) { $f.Group } else { $f.User }
                    foreach ($a in @($scope.assignments | Where-Object { $_.title -eq $who -or $_.loginName -eq $who })) {
                        $a.roles = @($a.roles | Where-Object { $_ -ne $f.Role })
                    }
                }
            }
        }
        $s
    }
}

Describe 'Sharing capabilities (Learn order)' {
    It 'orders Only people in your organization < Existing guests < New and existing guests < Anyone' {
        Compare-MgSharingCapability 'Disabled' 'ExistingExternalUserSharingOnly' | Should -Be -1
        Compare-MgSharingCapability 'ExistingExternalUserSharingOnly' 'ExternalUserSharingOnly' | Should -Be -1
        Compare-MgSharingCapability 'ExternalUserAndGuestSharing' 'ExternalUserSharingOnly' | Should -Be 1
        Compare-MgSharingCapability 'Disabled' 'Disabled' | Should -Be 0
        Get-MgSharingLabel 'ExternalUserAndGuestSharing' | Should -Be 'Anyone'
        { Compare-MgSharingCapability 'Public' 'Disabled' } | Should -Throw '*Unknown sharing capability*'
    }
}

Describe 'Test-MgGovernancePolicy' {
    It 'the purchasing policy only asks for the label id' {
        Rules (Test-MgGovernancePolicy -Policy $policy) | Should -Be @('GP006')
        $p = Copy-Json $policy; $p.sensitivityLabel.id = $labelId
        @(Test-MgGovernancePolicy -Policy $p) | Should -HaveCount 0
    }

    It 'finds every mistake in the loose policy: 5 errors, 2 warnings' {
        $f = @(Test-MgGovernancePolicy -Policy $bad)
        @($f | Where-Object Severity -eq 'Error') | Should -HaveCount 5
        @($f | Where-Object Severity -eq 'Warning') | Should -HaveCount 2
        Rules $f | Sort-Object -Unique | Should -Be @('GP001', 'GP002', 'GP004', 'GP005', 'GP006', 'GP007')
        ($f | Where-Object Rule -eq 'GP002').Message | Should -BeLike "*'Anyone' is more than 'New and existing guests'*"
    }

    It 'GP003: an Anyone default link on a site that cannot create Anyone links' {
        $p = Copy-Json $policy; $p.sharing.defaultLinkType = 'AnonymousAccess'
        Rules (Test-MgGovernancePolicy -Policy $p) | Should -Contain 'GP003'
    }

    It 'GP005: above 5,000 is a warning, above 50,000 an error' {
        $p = Copy-Json $policy; $p.uniquePermissions.maxItemScopesPerList = 5001
        ($p | ForEach-Object { Test-MgGovernancePolicy -Policy $_ } | Where-Object Rule -eq 'GP005').Severity | Should -Be 'Warning'
        $p.uniquePermissions.maxItemScopesPerList = 50001
        ($p | ForEach-Object { Test-MgGovernancePolicy -Policy $_ } | Where-Object Rule -eq 'GP005').Severity | Should -Be 'Error'
    }
}

Describe 'Test-MgPermissionSnapshot (the drifted lab site)' {
    It 'finds 4 errors and 8 warnings, 11 of them fixable' {
        $f = Audit $drifted
        @($f | Where-Object Severity -eq 'Error') | Should -HaveCount 4
        @($f | Where-Object Severity -eq 'Warning') | Should -HaveCount 8
        @($f | Where-Object Fix) | Should -HaveCount 11
        Rules $f | Sort-Object | Should -Be @('GV001', 'GV002', 'GV003', 'GV004', 'GV005', 'GV007', 'GV008', 'GV009', 'GV010', 'GV011', 'GV012', 'GV014')
    }

    It 'ignores Limited Access: SharePoint assigns it, nobody granted it' {
        $f = Audit $drifted
        @($f | Where-Object { $_.Message -like "*Sam Demo*" -and $_.Target -eq 'site' }) | Should -HaveCount 0
        @($f | Where-Object { $_.Message -like '*Contract Managers*Limited*' }) | Should -HaveCount 0
    }

    It 'after the remediation plan only the human decision is left: a second owner' {
        $plan = @(Get-MgRemediationPlan -Findings (Audit $drifted))
        $after = Invoke-PlanOnSnapshot $drifted $plan
        Rules (Audit $after) | Should -Be @('GV005')
    }

    It 'GV004: a different label is an error, the same label is fine' {
        $s = Copy-Json $drifted; $s.sensitivityLabel = '11111111-1111-1111-1111-111111111111'
        (Audit $s | Where-Object Rule -eq 'GV004').Message | Should -BeLike '*wants*Confidential*'
        $s.sensitivityLabel = $labelId
        Rules (Audit $s) | Should -Not -Contain 'GV004'
    }

    It 'GV007: Everyone except external users granted directly on a list' {
        $s = Copy-Json $drifted
        ($s.scopes | Where-Object title -eq 'Supplier Documents').assignments += Principal 'Everyone except external users' 'SecurityGroup' @('Read') 'c:0-.f|rolemanager|spo-grid-all-users/00000000-0000-0000-0000-000000000000'
        $g = Audit $s | Where-Object { $_.Rule -eq 'GV007' -and $_.Target -eq "list 'Supplier Documents'" }
        $g.Fix.Action | Should -Be 'RemoveGrant'
        $g.Fix.Kind | Should -Be 'List'
        $g.Fix.Role | Should -Be 'Read'
    }

    It 'GV015: a guest is an error only when the policy allows no external sharing' {
        $s = Copy-Json $drifted
        ($s.groups | Where-Object title -eq 'Contoso Purchasing Members').members += Principal 'Pat Supplier' 'User' @() 'i:0#.f|membership|pat_fabrikam.com#ext#@contoso.onmicrosoft.com'
        Rules (Audit $s) | Should -Contain 'GV015'
        $p = Copy-Json $policy; $p.sharing.capability = 'ExistingExternalUserSharingOnly'
        Rules (Audit $s $p) | Should -Not -Contain 'GV015'
    }

    It 'GV013: policy maximum, recommended 5,000 and supported 50,000 unique items per list' {
        $s = Copy-Json $drifted
        $items = foreach ($i in 1..51) { [pscustomobject]@{ kind = 'Item'; path = "f$i.txt"; list = 'Supplier Documents'; id = 100 + $i; unique = $true; assignments = @() } }
        $s.scopes = @($s.scopes) + @($items)
        (Audit $s | Where-Object Rule -eq 'GV013').Message | Should -BeLike '*the policy allows 50*'
        $p = Copy-Json $policy; $p.uniquePermissions.maxItemScopesPerList = 60
        Rules (Audit $s $p) | Should -Not -Contain 'GV013'
    }

    It 'GV014: an Anyone link is an error' {
        $s = Copy-Json $drifted
        $s.sharingLinks[0].scope = 'Anonymous'
        (Audit $s | Where-Object Rule -eq 'GV014').Severity | Should -Be 'Error'
    }
}

Describe 'Get-MgRemediationPlan' {
    It 'merges site settings into one call and orders links, items, grants, lists, members' {
        $plan = @(Get-MgRemediationPlan -Findings (Audit $drifted))
        $plan | Should -HaveCount 7
        $plan[0].Fix.Action | Should -Be 'SetSite'
        $plan[0].Fix.SharingCapability | Should -Be 'Disabled'
        $plan[0].Fix.SensitivityLabel | Should -Be $labelId
        @($plan | ForEach-Object { $_.Fix.Action }) | Should -Be @('SetSite', 'RemoveSharingLink', 'ResetItemInheritance', 'RemoveGrant', 'RemoveGrant', 'ResetListInheritance', 'RemoveGroupMember')
    }

    It 'drops grant removals on a list whose inheritance is reset (Purchase Requests)' {
        $plan = @(Get-MgRemediationPlan -Findings (Audit $drifted))
        @($plan | Where-Object { $_.Fix.Action -eq 'RemoveGrant' -and $_.Fix.PSObject.Properties['List'] -and $_.Fix.List -eq 'Purchase Requests' }) | Should -HaveCount 0
    }

    It 'an empty audit gives an empty plan' {
        @(Get-MgRemediationPlan -Findings @()) | Should -HaveCount 0
    }
}

Describe 'Invoke-Governance.ps1 (offline modes)' {
    It 'lints, audits the snapshot and prints the plan without a tenant' {
        $out = & (Join-Path $PSScriptRoot '..' 'src' 'Invoke-Governance.ps1') -PolicyPath (Join-Path $PSScriptRoot '..' 'src' 'governance' 'purchasing.policy.json') `
            -SnapshotPath (Join-Path $PSScriptRoot '..' 'src' 'fixtures' 'drifted.snapshot.json') -SensitivityLabelId $labelId 6>&1 | Out-String
        $out | Should -BeLike '*4 error(s), 8 warning(s); 11 can be fixed automatically*'
        $out | Should -BeLike '*ResetListInheritance*Purchase Requests*'
    }

    It 'refuses to audit with a policy that has errors' {
        { & (Join-Path $PSScriptRoot '..' 'src' 'Invoke-Governance.ps1') -PolicyPath (Join-Path $PSScriptRoot '..' 'src' 'bad' 'loose.policy.json') `
                -SnapshotPath (Join-Path $PSScriptRoot '..' 'src' 'fixtures' 'drifted.snapshot.json') 6>$null } | Should -Throw '*policy has errors*'
    }
}

Describe 'Tenant functions (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
        $script:site = 'https://contoso.sharepoint.com/sites/Purchasing'
        $script:writeCmds = 'Set-PnPTenantSite', 'Remove-PnPFileSharingLink', 'Set-PnPListItemPermission', 'Set-PnPList', 'Remove-PnPGroupMember',
            'Set-PnPWebPermission', 'Set-PnPListPermission'
        function User($t, $l) { [pscustomobject]@{ Title = $t; LoginName = $l; PrincipalType = 'User' } }
    }

    It 'Get-MgPermissionSnapshot reads settings, groups, scopes and links into the audit model' {
        Mock -ModuleName MgGovernance Get-PnPTenantSite { [pscustomobject]@{ SharingCapability = 'ExistingExternalUserSharingOnly'; DefaultSharingLinkType = 'Internal'; DefaultLinkPermission = 'Edit'; SensitivityLabel = '00000000-0000-0000-0000-000000000000' } }
        Mock -ModuleName MgGovernance Get-PnPWeb { [pscustomobject]@{ Title = 'Contoso Purchasing'; ServerRelativeUrl = '/sites/Purchasing'; HasUniqueRoleAssignments = $true } }
        Mock -ModuleName MgGovernance Get-PnPGroup -ParameterFilter { $AssociatedOwnerGroup } { [pscustomobject]@{ Title = 'Contoso Purchasing Owners' } }
        Mock -ModuleName MgGovernance Get-PnPGroup -ParameterFilter { $AssociatedMemberGroup } { [pscustomobject]@{ Title = 'Contoso Purchasing Members' } }
        Mock -ModuleName MgGovernance Get-PnPGroup -ParameterFilter { $AssociatedVisitorGroup } { [pscustomobject]@{ Title = 'Contoso Purchasing Visitors' } }
        Mock -ModuleName MgGovernance Get-PnPGroup { 'Contoso Purchasing Owners', 'Contoso Purchasing Members', 'Contoso Purchasing Visitors' | ForEach-Object { [pscustomobject]@{ Title = $_ } } }
        Mock -ModuleName MgGovernance Get-PnPGroupMember { if ("$Group" -like '*Owners') { User 'Lab Admin' 'i:0#.f|membership|labadmin@contoso.com' } }
        Mock -ModuleName MgGovernance Get-PnPSiteCollectionAdmin { User 'Lab Admin' 'i:0#.f|membership|labadmin@contoso.com' }
        Mock -ModuleName MgGovernance Get-PnPList {
            [pscustomobject]@{ Id = [guid]'11111111-0000-0000-0000-000000000001'; Title = 'Supplier Documents'; HasUniqueRoleAssignments = $true; ItemCount = 2; Hidden = $false; BaseType = 'DocumentLibrary' }
            [pscustomobject]@{ Id = [guid]'11111111-0000-0000-0000-000000000002'; Title = 'Hidden Stuff'; HasUniqueRoleAssignments = $true; ItemCount = 1; Hidden = $true; BaseType = 'GenericList' }
        }
        Mock -ModuleName MgGovernance Get-PnPListItem {
            @{ Id = 7; FileRef = '/sites/Purchasing/SupplierDocuments/Fabrikam/CTR-2026-0042 Fabrikam.txt'; FileLeafRef = 'CTR-2026-0042 Fabrikam.txt'; FSObjType = 0; HasUniqueRoleAssignments = $true }
            @{ Id = 8; FileRef = '/sites/Purchasing/SupplierDocuments/Fabrikam'; FileLeafRef = 'Fabrikam'; FSObjType = 1; HasUniqueRoleAssignments = $false }
        }
        Mock -ModuleName MgGovernance Get-PnPFileSharingLink {
            [pscustomobject]@{ Id = 'link-1'; Link = [pscustomobject]@{ Scope = 'Organization'; Type = 'Edit' }; ExpirationDateTime = [datetime]::MinValue }
            [pscustomobject]@{ Id = 'direct-1'; Link = $null; ExpirationDateTime = [datetime]::MinValue }
        }
        Mock -ModuleName MgGovernance Get-MgRoleAssignment { [pscustomobject]@{ title = 'Contoso Purchasing Owners'; loginName = 'Contoso Purchasing Owners'; principalType = 'SharePointGroup'; roles = @('Full Control') } }

        $s = Get-MgPermissionSnapshot -SiteUrl $site
        $s.sharingCapability | Should -Be 'ExistingExternalUserSharingOnly'
        $s.sensitivityLabel | Should -BeNullOrEmpty
        $s.associatedGroups.Visitors | Should -Be 'Contoso Purchasing Visitors'
        @($s.scopes | ForEach-Object kind) | Should -Be @('Web', 'List', 'Item')
        ($s.scopes | Where-Object kind -eq 'Item').id | Should -Be 7
        @($s.sharingLinks) | Should -HaveCount 1
        $s.sharingLinks[0].scope | Should -Be 'Organization'
        $s.sharingLinks[0].expires | Should -BeNullOrEmpty
        Should -Invoke -ModuleName MgGovernance Get-PnPListItem -Times 1 -Exactly -ParameterFilter { "$List" -ne '' -and $Includes -contains 'HasUniqueRoleAssignments' }
        Should -Invoke -ModuleName MgGovernance Get-PnPFileSharingLink -Times 1 -Exactly -ParameterFilter { "$Identity" -like '*CTR-2026-0042*' -or $Identity.ServerRelativeUrl -like '*CTR-2026-0042*' }
        Rules (Audit $s) | Should -Contain 'GV001'
    }

    It 'Invoke-MgRemediation calls the right cmdlet for every fix' {
        foreach ($c in $writeCmds) { Mock -ModuleName MgGovernance $c { } }
        $plan = @(Get-MgRemediationPlan -Findings (Audit $drifted))
        $rows = @(Invoke-MgRemediation -SiteUrl $site -Plan $plan)
        @($rows | Where-Object Done) | Should -HaveCount 7
        Should -Invoke -ModuleName MgGovernance Set-PnPTenantSite -Times 1 -Exactly -ParameterFilter {
            "$SharingCapability" -eq 'Disabled' -and "$DefaultSharingLinkType" -eq 'Direct' -and "$DefaultLinkPermission" -eq 'View' -and $SensitivityLabel -eq $labelId }
        Should -Invoke -ModuleName MgGovernance Remove-PnPFileSharingLink -Times 1 -Exactly -ParameterFilter { $Identity -eq '00000000-0000-0000-0000-000000000001' -and $Force }
        Should -Invoke -ModuleName MgGovernance Set-PnPListItemPermission -Times 1 -Exactly -ParameterFilter { $InheritPermissions -and "$List" -eq 'Supplier Documents' }
        Should -Invoke -ModuleName MgGovernance Set-PnPListPermission -Times 1 -Exactly -ParameterFilter { $Group.Name -eq 'Contoso Purchasing Members' -and $RemoveRole -eq 'Edit' }
        Should -Invoke -ModuleName MgGovernance Set-PnPWebPermission -Times 1 -Exactly -ParameterFilter { $User -like '*alex.demo*' -and $RemoveRole -contains 'Full Control' }
        Should -Invoke -ModuleName MgGovernance Set-PnPList -Times 1 -Exactly -ParameterFilter { $ResetRoleInheritance -and "$Identity" -eq 'Purchase Requests' }
        Should -Invoke -ModuleName MgGovernance Remove-PnPGroupMember -Times 1 -Exactly -ParameterFilter { $Group.Name -eq 'Contoso Purchasing Visitors' }
    }

    It '-WhatIf writes nothing' {
        foreach ($c in $writeCmds) { Mock -ModuleName MgGovernance $c { throw 'WhatIf violated' } }
        $rows = @(Invoke-MgRemediation -SiteUrl $site -Plan @(Get-MgRemediationPlan -Findings (Audit $drifted)) -WhatIf)
        @($rows | Where-Object Done) | Should -HaveCount 0
        $rows | Should -HaveCount 7
    }

    It 'New-PermissionDrift.ps1 creates the drift the audit expects' {
        Mock Connect-PnPOnline { $null }
        Mock Set-PnPTenantSite { }
        Mock Set-PnPWebPermission { }
        Mock Get-PnPList { [pscustomobject]@{ Title = "$Identity" } }
        Mock Set-PnPList { }
        Mock Set-PnPListPermission { }
        Mock Get-PnPGroup { $null }
        Mock New-PnPGroup { [pscustomobject]@{ Title = $Title } }
        Mock Add-PnPGroupMember { }
        Mock Get-PnPListItem {
            @{ Id = 7; FileRef = '/sites/Purchasing/SupplierDocuments/Fabrikam/CTR-2026-0042 Fabrikam until 2026-12-21.txt'; FileLeafRef = 'CTR-2026-0042 Fabrikam until 2026-12-21.txt'; FSObjType = 0 }
            @{ Id = 9; FileRef = '/sites/Purchasing/SupplierDocuments/Northwind Traders/INV-10022 Northwind Traders 2026-11-06.txt'; FileLeafRef = 'INV-10022 Northwind Traders 2026-11-06.txt'; FSObjType = 0 }
        }
        Mock Set-PnPListItemPermission { }
        Mock Add-PnPFileOrganizationalSharingLink { }
        & (Join-Path $PSScriptRoot '..' 'src' 'New-PermissionDrift.ps1') -SiteUrl $site -ClientId ([guid]::Empty) -DirectUser 'alex.demo@contoso.com' `
            -ShareWithUser 'sam.demo@contoso.com' -ContractManager 'jordan.demo@contoso.com' 6>$null
        Should -Invoke Set-PnPTenantSite -Times 1 -Exactly -ParameterFilter { "$SharingCapability" -eq 'ExistingExternalUserSharingOnly' -and "$DefaultSharingLinkType" -eq 'Internal' }
        Should -Invoke Set-PnPWebPermission -Times 1 -Exactly -ParameterFilter { $User -eq 'alex.demo@contoso.com' -and $AddRole -contains 'Full Control' }
        Should -Invoke Set-PnPList -Times 2 -Exactly -ParameterFilter { $BreakRoleInheritance -and $CopyRoleAssignments }
        Should -Invoke New-PnPGroup -Times 1 -Exactly -ParameterFilter { $Title -eq 'Contract Managers' }
        Should -Invoke Set-PnPListPermission -Times 1 -Exactly -ParameterFilter { $Group.Name -eq 'Contract Managers' -and $AddRole -eq 'Contribute' }
        Should -Invoke Set-PnPListItemPermission -Times 1 -Exactly -ParameterFilter { "$Identity" -eq '7' -or $Identity.Id -eq 7 }
        Should -Invoke Add-PnPFileOrganizationalSharingLink -Times 1 -Exactly -ParameterFilter { $FileUrl -like '*INV-10022*' -and "$ShareType" -eq 'Edit' }
    }

    It 'New-PermissionDrift.ps1 -WhatIf changes nothing' {
        Mock Connect-PnPOnline { $null }
        foreach ($c in 'Set-PnPTenantSite', 'Set-PnPWebPermission', 'Set-PnPList', 'Set-PnPListPermission', 'New-PnPGroup', 'Add-PnPGroupMember', 'Set-PnPListItemPermission', 'Add-PnPFileOrganizationalSharingLink') {
            Mock $c { throw 'WhatIf violated' }
        }
        Mock Get-PnPList { [pscustomobject]@{ Title = "$Identity" } }
        Mock Get-PnPListItem { @{ Id = 7; FileRef = '/x/CTR-1 Fabrikam.txt'; FileLeafRef = 'CTR-1 Fabrikam.txt'; FSObjType = 0 } }
        { & (Join-Path $PSScriptRoot '..' 'src' 'New-PermissionDrift.ps1') -SiteUrl $site -ClientId ([guid]::Empty) -DirectUser 'a@contoso.com' `
                -ShareWithUser 'b@contoso.com' -ContractManager 'c@contoso.com' -WhatIf 6>$null 3>$null } | Should -Not -Throw
    }
}
