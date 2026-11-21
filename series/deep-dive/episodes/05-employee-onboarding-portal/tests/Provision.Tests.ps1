BeforeAll {
    # Stubs so PnP.PowerShell and Microsoft Graph PowerShell calls can be mocked without the modules installed.
    if (-not (Get-Command Get-PnPList -ErrorAction SilentlyContinue)) {
        function global:Get-PnPList { [CmdletBinding()] param($Identity) }
        function global:New-PnPList { [CmdletBinding()] param($Title, $Template, [switch] $EnableVersioning) }
        function global:Set-PnPList { [CmdletBinding()] param($Identity, $Description) }
        function global:Get-PnPField { [CmdletBinding()] param($List, $Identity) }
        function global:Add-PnPFieldFromXml { [CmdletBinding()] param($List, $FieldXml) }
    }
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        function global:Invoke-MgGraphRequest { [CmdletBinding()] param($Method, $Uri, $Body, $OutputType, $ContentType) }
    }
    Import-Module (Join-Path $PSScriptRoot '..' 'provision' 'OnboardingLists.psm1') -Force
    Import-Module (Join-Path $PSScriptRoot '..' 'provision' 'OnboardingAccess.psm1') -Force
    $script:ContractPath = Join-Path $PSScriptRoot '..' 'contract' 'onboarding-lists.json'
}

Describe 'List contract' {
    It 'has the two lists and an indexed status column' {
        $c = Read-OnboardingContract -Path $script:ContractPath
        $c.lists.title | Should -Be @('Onboarding Requests', 'Onboarding Tasks')
        ($c.lists[0].columns | Where-Object internalName -eq 'OnbStatus').indexed | Should -BeTrue
        ($c.lists[1].columns | Where-Object internalName -eq 'OnbRequestId').indexed | Should -BeTrue
    }
    It 'refuses duplicates and internal names SharePoint would mangle' {
        $tmp = New-TemporaryFile
        '{"lists":[{"title":"X","columns":[{"internalName":"A","type":"Text"},{"internalName":"A","type":"Text"}]}]}' | Set-Content $tmp
        { Read-OnboardingContract -Path $tmp } | Should -Throw '*Duplicate*'
        '{"lists":[{"title":"X","columns":[{"internalName":"Start date","type":"Text"}]}]}' | Set-Content $tmp
        { Read-OnboardingContract -Path $tmp } | Should -Throw '*letters/digits*'
        Remove-Item $tmp
    }
}

Describe 'ConvertTo-OnboardingFieldXml' {
    BeforeAll { $script:C = Read-OnboardingContract -Path $script:ContractPath }
    It 'produces valid CAML for every contract column' {
        foreach ($col in $script:C.lists.columns) {
            $xml = [xml](ConvertTo-OnboardingFieldXml -Column $col)
            $xml.Field.Name | Should -Be $col.internalName
            $xml.Field.StaticName | Should -Be $col.internalName
        }
    }
    It 'builds the status choice with default, choices and index' {
        $xml = [xml](ConvertTo-OnboardingFieldXml -Column ($script:C.lists[0].columns | Where-Object internalName -eq 'OnbStatus'))
        $xml.Field.Type | Should -Be 'Choice'
        $xml.Field.Indexed | Should -Be 'TRUE'
        $xml.Field.Default | Should -Be 'Submitted'
        $xml.Field.CHOICES.CHOICE | Should -Be @('Submitted', 'Approved', 'Rejected', 'Sent to Entra', 'Account created', 'Failed')
    }
    It 'maps date-only and required columns' {
        $xml = [xml](ConvertTo-OnboardingFieldXml -Column ($script:C.lists[0].columns | Where-Object internalName -eq 'OnbStartDate'))
        $xml.Field.Type | Should -Be 'DateTime'
        $xml.Field.Format | Should -Be 'DateOnly'
        $xml.Field.Required | Should -Be 'TRUE'
    }
    It 'escapes XML and rejects unknown types' {
        ([xml](ConvertTo-OnboardingFieldXml -Column ([pscustomobject]@{ internalName = 'X'; displayName = 'A & <B>'; type = 'Text' }))).Field.DisplayName | Should -Be 'A & <B>'
        { ConvertTo-OnboardingFieldXml -Column ([pscustomobject]@{ internalName = 'X'; displayName = 'X'; type = 'Lookup' }) } | Should -Throw '*Unsupported*'
    }
}

Describe 'Install-OnboardingLists' {
    BeforeEach { $script:C = Read-OnboardingContract -Path $script:ContractPath }
    It 'creates both lists and every column on an empty site' {
        Mock -ModuleName OnboardingLists Get-PnPList { $null }
        Mock -ModuleName OnboardingLists New-PnPList { }
        Mock -ModuleName OnboardingLists Set-PnPList { }
        Mock -ModuleName OnboardingLists Get-PnPField { $null }
        Mock -ModuleName OnboardingLists Add-PnPFieldFromXml { }
        $r = @(Install-OnboardingLists -Contract $script:C)
        Should -Invoke -ModuleName OnboardingLists New-PnPList -Times 2 -Exactly
        Should -Invoke -ModuleName OnboardingLists Add-PnPFieldFromXml -Times 19 -Exactly
        ($r | Where-Object Result -eq 'Added').Count | Should -Be 21
    }
    It 'is idempotent: a second run changes nothing' {
        Mock -ModuleName OnboardingLists Get-PnPList { [pscustomobject]@{ Title = $Identity } }
        Mock -ModuleName OnboardingLists Get-PnPField { [pscustomobject]@{} }
        Mock -ModuleName OnboardingLists New-PnPList { }
        Mock -ModuleName OnboardingLists Add-PnPFieldFromXml { }
        $r = @(Install-OnboardingLists -Contract $script:C)
        ($r | Where-Object Result -ne 'Exists') | Should -BeNullOrEmpty
        Should -Invoke -ModuleName OnboardingLists New-PnPList -Times 0 -Exactly
        Should -Invoke -ModuleName OnboardingLists Add-PnPFieldFromXml -Times 0 -Exactly
    }
    It '-WhatIf changes nothing' {
        Mock -ModuleName OnboardingLists Get-PnPList { $null }
        Mock -ModuleName OnboardingLists New-PnPList { }
        Mock -ModuleName OnboardingLists Add-PnPFieldFromXml { }
        Install-OnboardingLists -Contract $script:C -WhatIf | Out-Null
        Should -Invoke -ModuleName OnboardingLists New-PnPList -Times 0 -Exactly
        Should -Invoke -ModuleName OnboardingLists Add-PnPFieldFromXml -Times 0 -Exactly
    }
}

Describe 'Grant-OnbGraphAppRoles' {
    BeforeEach {
        $script:Posts = [System.Collections.Generic.List[object]]::new()
        Mock -ModuleName OnboardingAccess Invoke-MgGraphRequest {
            if ($Method -eq 'POST') { $script:Posts.Add(@{ Uri = $Uri; Body = ($Body | ConvertFrom-Json) }); return [pscustomobject]@{} }
            if ($Uri -like "*appId eq '00000003-0000-0000-c000-000000000000'*" -or $Uri -like '*appId%20eq%20%2700000003-0000-0000-c000-000000000000%27*') {
                return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'graph-sp'; appRoles = @(
                    [pscustomobject]@{ id = 'r-upload'; value = 'SynchronizationData-User.Upload'; allowedMemberTypes = @('Application') },
                    [pscustomobject]@{ id = 'r-users'; value = 'User.Read.All'; allowedMemberTypes = @('Application') },
                    [pscustomobject]@{ id = 'r-lists'; value = 'Lists.SelectedOperations.Selected'; allowedMemberTypes = @('Application') },
                    [pscustomobject]@{ id = 'r-rw'; value = 'User.ReadWrite.All'; allowedMemberTypes = @('Application') }) }) }
            }
            if ($Uri -like '*/servicePrincipals/mi-sp/appRoleAssignments') {
                return [pscustomobject]@{ value = @([pscustomobject]@{ resourceId = 'graph-sp'; appRoleId = 'r-users' }) }
            }
            if ($Uri -like '*servicePrincipals`?*') { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'mi-sp'; displayName = 'id-onb' }) } }
            throw "unexpected $Method $Uri"
        }
    }
    It 'assigns only the missing roles, never a broader one' {
        $r = @(Grant-OnbGraphAppRoles -IdentityClientId '00000000-0000-0000-0000-000000000009')
        ($r | Where-Object Result -eq 'Exists').Grant | Should -Be 'User.Read.All'
        ($r | Where-Object Result -eq 'Added').Grant | Should -Be @('SynchronizationData-User.Upload', 'Lists.SelectedOperations.Selected')
        $script:Posts.Count | Should -Be 2
        $script:Posts[0].Uri | Should -BeLike '*/servicePrincipals/mi-sp/appRoleAssignments'
        $script:Posts[0].Body.principalId | Should -Be 'mi-sp'
        $script:Posts[0].Body.resourceId | Should -Be 'graph-sp'
        $script:Posts.Body.appRoleId | Should -Not -Contain 'r-rw'
    }
    It 'requests exactly the three documented roles' {
        Get-OnbRequiredGraphRoles | Should -Be @('SynchronizationData-User.Upload', 'User.Read.All', 'Lists.SelectedOperations.Selected')
    }
    It 'fails on a role Graph does not have' {
        { Grant-OnbGraphAppRoles -IdentityClientId 'x' -Roles 'Not.A.Role' } | Should -Throw '*no application role*'
    }
    It '-WhatIf posts nothing' {
        Grant-OnbGraphAppRoles -IdentityClientId 'x' -WhatIf | Out-Null
        $script:Posts.Count | Should -Be 0
    }
}

Describe 'Grant-OnbListAccess and Resolve-OnbListIds' {
    It 'adds a write grant for the identity on one list' {
        $script:Posted = $null
        Mock -ModuleName OnboardingAccess Invoke-MgGraphRequest {
            if ($Method -eq 'POST') { $script:Posted = $Body | ConvertFrom-Json; return [pscustomobject]@{} }
            [pscustomobject]@{ value = @([pscustomobject]@{ roles = @('read'); grantedToV2 = [pscustomobject]@{ application = [pscustomobject]@{ id = 'someone-else' } } }) }
        }
        (Grant-OnbListAccess -SiteId 's' -ListId 'l' -IdentityClientId 'client-1' -DisplayName 'id-onb').Result | Should -Be 'Added'
        $script:Posted.roles | Should -Be @('write')
        $script:Posted.grantedToV2.application.id | Should -Be 'client-1'
    }
    It 'reports an existing grant instead of adding another' {
        Mock -ModuleName OnboardingAccess Invoke-MgGraphRequest {
            if ($Method -eq 'POST') { throw 'should not post' }
            [pscustomobject]@{ value = @([pscustomobject]@{ roles = @('write'); grantedToV2 = [pscustomobject]@{ application = [pscustomobject]@{ id = 'client-1' } } }) }
        }
        (Grant-OnbListAccess -SiteId 's' -ListId 'l' -IdentityClientId 'client-1' -DisplayName 'id-onb').Result | Should -Be 'Exists'
    }
    It 'resolves site and list IDs, and explains a missing list' {
        Mock -ModuleName OnboardingAccess Invoke-MgGraphRequest {
            if ($Uri -like '*/sites/contoso.sharepoint.com:/sites/hr-lab') { return [pscustomobject]@{ id = 'site-1' } }
            if ($Uri -like '*Onboarding%20Requests*') { return [pscustomobject]@{ value = @([pscustomobject]@{ id = 'list-r' }) } }
            [pscustomobject]@{ value = @() }
        }
        $ids = Resolve-OnbListIds -HostName 'contoso.sharepoint.com' -SitePath '/sites/hr-lab' -ListTitles 'Onboarding Requests'
        $ids.SiteId | Should -Be 'site-1'
        $ids['Onboarding Requests'] | Should -Be 'list-r'
        { Resolve-OnbListIds -HostName 'contoso.sharepoint.com' -SitePath '/sites/hr-lab' -ListTitles 'Onboarding Tasks' } | Should -Throw '*New-OnboardingLists*'
    }
}

Describe 'Entry scripts parse' {
    It '<_> is valid PowerShell' -ForEach @('New-OnboardingLists.ps1', 'Grant-OnboardingAccess.ps1') {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..' 'provision' $_), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}
