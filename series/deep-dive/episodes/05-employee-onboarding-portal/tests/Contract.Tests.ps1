# The lists, the canvas app, the approval flow, the function and the Bicep must agree on names and statuses.
BeforeAll {
    $script:Root = Join-Path $PSScriptRoot '..'
    $script:Contract = Get-Content (Join-Path $script:Root 'contract' 'onboarding-lists.json') -Raw | ConvertFrom-Json
    $script:Requests = $script:Contract.lists | Where-Object title -eq 'Onboarding Requests'
    $script:Tasks = $script:Contract.lists | Where-Object title -eq 'Onboarding Tasks'
    $script:StatusChoices = ($script:Requests.columns | Where-Object internalName -eq 'OnbStatus').choices
    $script:AllInternal = @($script:Contract.lists.columns.internalName)
    $script:ModuleText = Get-Content (Join-Path $script:Root 'src' 'OnboardingSync' 'Modules' 'OnboardingSync' 'OnboardingSync.psm1') -Raw
    $script:Flow = Get-Content (Join-Path $script:Root 'flow' 'onboarding-approval.definition.json') -Raw
    $script:App = Get-Content (Join-Path $script:Root 'app' 'onboarding-portal.powerfx.json') -Raw | ConvertFrom-Json
    $json = & bicep build (Join-Path $script:Root 'infra' 'main.bicep') --stdout
    if ($LASTEXITCODE -ne 0) { throw 'bicep build failed' }
    $script:Arm = $json | Out-String | ConvertFrom-Json -Depth 50
    $script:Site = $script:Arm.resources | Where-Object type -eq 'Microsoft.Web/sites'
    $script:Settings = ($script:Arm.resources | Where-Object type -eq 'Microsoft.Web/sites/config').properties
}

Describe 'Statuses' {
    It 'the contract statuses and the status column choices are the same list' {
        @($script:Contract.statuses.PSObject.Properties.Value) | Should -Be $script:StatusChoices
    }
    It 'every status the function writes or reads is a choice' {
        foreach ($s in [regex]::Matches($script:ModuleText, "OnbStatus = '([^']+)'|-Value '([^']+)'") | ForEach-Object { ($_.Groups[1].Value, $_.Groups[2].Value) -ne '' }) {
            $script:StatusChoices | Should -Contain $s
        }
    }
    It 'the flow starts on Submitted and writes only Approved or Rejected' {
        $script:Flow | Should -Match "'body/OnbStatus/Value'\], 'Submitted'"
        $written = [regex]::Matches($script:Flow, '"item/OnbStatus/Value": "([^"]+)"') | ForEach-Object { $_.Groups[1].Value }
        $written | Should -Be @('Approved', 'Rejected')
    }
    It 'the app creates items as Submitted' {
        $script:App.screens.NewRequestScreen.'btnSubmit.OnSelect' | Should -Match 'Status: \{Value: "Submitted"\}'
    }
}

Describe 'Column names' {
    It 'every OnbXxx name in the function exists in the contract' {
        $used = [regex]::Matches($script:ModuleText, '(?<![-\w])Onb[A-Z][A-Za-z]+\b') | ForEach-Object Value | Sort-Object -Unique |
            Where-Object { $_ -notmatch '^Onb(ValidationException)$' }
        foreach ($n in $used) { $script:AllInternal | Should -Contain $n -Because "the function uses $n" }
    }
    It 'every column the flow reads or writes exists (or is a SharePoint built-in)' {
        $builtIn = @('ID', 'Title', 'Author', '{Link}')
        $names = [regex]::Matches($script:Flow, "(?:body|item)/([A-Za-z{}]+)") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique |
            Where-Object { $_ -notin @('value', 'outcome', 'responses') }
        foreach ($n in $names) { ($builtIn + $script:AllInternal) | Should -Contain $n }
    }
    It 'every column the app patches is a display name in the contract' {
        $display = @($script:Requests.columns.displayName) + 'Title'
        $patch = $script:App.screens.NewRequestScreen.'btnSubmit.OnSelect'
        $record = [regex]::Match($patch, '\{\s*\n(?<body>[\s\S]+?)\n\s*\}\s*\n\);').Groups['body'].Value
        $keys = [regex]::Matches($record, "^\s*('(?<q>[^']+)'|(?<p>[A-Za-z]+)):", 'Multiline') | ForEach-Object { if ($_.Groups['q'].Success) { $_.Groups['q'].Value } else { $_.Groups['p'].Value } }
        $keys.Count | Should -Be 9
        foreach ($k in $keys) { $display | Should -Contain $k }
    }
    It 'every quoted column the app reads is a display name (or a SharePoint built-in)' {
        $display = @($script:Requests.columns.displayName) + @('Created By', 'Onboarding Requests')
        $all = ($script:App.screens.PSObject.Properties.Value | ForEach-Object { $_.PSObject.Properties.Value }) -join "`n"
        foreach ($q in [regex]::Matches($all, "'([^']+)'") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique) {
            $display | Should -Contain $q
        }
    }
}

Describe 'Task templates' {
    BeforeAll { $script:Templates = Get-Content (Join-Path $script:Root 'src' 'OnboardingSync' 'config' 'task-templates.json') -Raw | ConvertFrom-Json }
    It 'owners are choices of the Owner column and keys are unique per department' {
        $owners = ($script:Tasks.columns | Where-Object internalName -eq 'OnbOwnerRole').choices
        $all = @($script:Templates.default) + @($script:Templates.byDepartment.PSObject.Properties.Value | ForEach-Object { $_ })
        foreach ($t in $all) { $owners | Should -Contain $t.owner }
        foreach ($dept in $script:Templates.byDepartment.PSObject.Properties.Name) {
            $keys = @($script:Templates.default.key) + @($script:Templates.byDepartment.$dept.key)
            ($keys | Sort-Object -Unique).Count | Should -Be $keys.Count
        }
    }
    It 'department keys are departments in the list, and the function knows the same departments' {
        $depts = ($script:Requests.columns | Where-Object internalName -eq 'OnbDepartment').choices
        foreach ($d in $script:Templates.byDepartment.PSObject.Properties.Name) { $depts | Should -Contain $d }
        $script:ModuleText | Should -Match ([regex]::Escape("Departments = @('" + ($depts -join "', '") + "')"))
    }
}

Describe 'Function app and Bicep' {
    It 'runs PowerShell 7.6 on Flex Consumption with a user-assigned identity' {
        $script:Site.properties.functionAppConfig.runtime.name | Should -Be 'powershell'
        $script:Site.properties.functionAppConfig.runtime.version | Should -Be '7.6'
        ($script:Arm.resources | Where-Object type -eq 'Microsoft.Web/serverfarms').sku.name | Should -Be 'FC1'
        $script:Site.identity.type | Should -Be 'UserAssigned'
    }
    It 'has no shared keys and only two Azure role assignments' {
        ($script:Arm.resources | Where-Object type -eq 'Microsoft.Storage/storageAccounts').properties.allowSharedKeyAccess | Should -BeFalse
        ($script:Arm.resources | Where-Object type -eq 'Microsoft.Insights/components').properties.DisableLocalAuth | Should -BeTrue
        @($script:Arm.resources | Where-Object type -eq 'Microsoft.Authorization/roleAssignments').Count | Should -Be 2
        $script:Settings.PSObject.Properties.Name | Where-Object { $_ -match 'Key|Secret|Password|ConnectionString$' -and $_ -ne 'APPLICATIONINSIGHTS_CONNECTION_STRING' } | Should -BeNullOrEmpty
    }
    It 'sets every app setting the function reads' {
        $read = [regex]::Matches($script:ModuleText, "'(Onboarding__[A-Za-z]+)'|env:(Onboarding__[A-Za-z]+)") |
            ForEach-Object { ($_.Groups[1].Value, $_.Groups[2].Value) -ne '' } | Sort-Object -Unique
        foreach ($s in $read) { $script:Settings.PSObject.Properties.Name | Should -Contain $s }
        $script:Settings.PSObject.Properties.Name | Should -Contain 'AZURE_CLIENT_ID'
    }
    It 'binds the timer to the schedule app setting' {
        $fj = Get-Content (Join-Path $script:Root 'src' 'OnboardingSync' 'SyncOnboarding' 'function.json') -Raw | ConvertFrom-Json
        $fj.bindings[0].type | Should -Be 'timerTrigger'
        $fj.bindings[0].schedule | Should -Be '%Onboarding__Schedule%'
        $script:Settings.PSObject.Properties.Name | Should -Contain 'Onboarding__Schedule'
    }
    It 'turns managed dependencies off (not supported on Flex Consumption)' {
        $hostJson = Get-Content (Join-Path $script:Root 'src' 'OnboardingSync' 'host.json') -Raw | ConvertFrom-Json
        $hostJson.managedDependency.enabled | Should -BeFalse
        Test-Path (Join-Path $script:Root 'src' 'OnboardingSync' 'requirements.psd1') | Should -BeFalse
    }
    It 'parses run.ps1 and the module without errors' {
        foreach ($f in @('SyncOnboarding/run.ps1', 'Modules/OnboardingSync/OnboardingSync.psm1', 'profile.ps1')) {
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $script:Root 'src' 'OnboardingSync' $f), [ref]$null, [ref]$errors) | Out-Null
            $errors | Should -BeNullOrEmpty -Because $f
        }
    }
}
