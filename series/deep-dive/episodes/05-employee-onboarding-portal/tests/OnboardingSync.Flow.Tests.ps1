# End-to-end passes of Invoke-OnbSync and run.ps1 against FakeGraph (an in-memory Graph, tests only).
BeforeAll {
    . (Join-Path $PSScriptRoot 'FakeGraph.ps1')
    $script:ModulesDir = Join-Path $PSScriptRoot '..' 'src' 'OnboardingSync' 'Modules'
    Import-Module (Join-Path $script:ModulesDir 'OnboardingSync') -Force
    $script:Templates = Get-Content (Join-Path $PSScriptRoot '..' 'src' 'OnboardingSync' 'config' 'task-templates.json') -Raw | ConvertFrom-Json
    $script:Now = [datetimeoffset]'2026-11-23T10:00:00Z'   # a Monday

    function New-World {
        $w = [FakeGraph]::new()
        $w.AddUser(@{ userPrincipalName = 'sam.demo@contoso.com'; mail = 'sam.demo@contoso.com'; employeeId = 'E1002'; accountEnabled = $true }) | Out-Null
        $w.AddUser(@{ userPrincipalName = 'taylor.demo@contoso.com'; mail = 'taylor.demo@contoso.com'; accountEnabled = $true }) | Out-Null
        return $w
    }
    function New-Config([FakeGraph] $w) {
        @{ SiteId = $w.SiteId; RequestsListId = $w.RequestsListId; TasksListId = $w.TasksListId
           ProvisioningServicePrincipalId = $w.SpId; ProvisioningJobId = $w.JobId; UpnDomain = 'contoso.com'
           TimeZoneId = 'Europe/Lisbon'; StartHour = 9; SentTimeoutMinutes = 60
           Departments = @('Sales', 'Finance', 'Operations', 'IT'); Templates = $script:Templates }
    }
    function New-RequestFields([string] $given = 'Casey', [string] $surname = 'Demo', [string] $manager = 'sam.demo@contoso.com', [string] $start = '2026-12-07T00:00:00Z') {
        @{ Title = "$given $surname"; OnbGivenName = $given; OnbSurname = $surname; OnbDepartment = 'Sales'; OnbJobTitle = 'Sales representative'
           OnbManagerEmail = $manager; OnbStartDate = $start; OnbUsageLocation = 'PT'; OnbStatus = 'Approved' }
    }
}

Describe 'OnboardingSync end to end' {
    BeforeEach {
        $script:World = New-World
        $global:OnbFakeWorld = $script:World
        $script:Config = New-Config $script:World
        Mock -ModuleName OnboardingSync Invoke-OnbGraph {
            $m = if ($PesterBoundParameters.ContainsKey('Method')) { $Method } else { 'GET' }
            $ct = if ($PesterBoundParameters.ContainsKey('ContentType')) { $ContentType } else { 'application/json' }
            $global:OnbFakeWorld.Invoke($m, $Path, $Body, $IfMatch, $ct)   # global: run.ps1 has its own script scope
        }
    }

    Describe 'Happy path: approved request to account to checklist' {
        It 'sends one SCIM operation, then records the account and creates the tasks once' {
            $item = $script:World.AddRequest((New-RequestFields))

            $r1 = Invoke-OnbSync -Config $script:Config -Now $script:Now
            $r1.To | Should -Be 'Sent to Entra'
            $req = $script:World.Request($item.Id)
            $req.Fields.OnbStatus | Should -Be 'Sent to Entra'
            $req.Fields.OnbEmployeeId | Should -Be 'NH00001'
            $req.Fields.OnbUpn | Should -Be 'casey.demo@contoso.com'
            $script:World.Staged.Count | Should -Be 1
            $script:World.Staged[0].data.externalId | Should -Be 'NH00001'

            # the provisioning service does its work
            $script:World.RunProvisioning()
            $user = $script:World.UserByEmployeeId('NH00001')
            $user.accountEnabled | Should -BeFalse
            $user.managerId | Should -Be ($script:World.Users | Where-Object employeeId -eq 'E1002').id
            $user.employeeHireDate | Should -Be '2026-12-07T09:00:00Z'
            $user.usageLocation | Should -Be 'PT'

            $r2 = Invoke-OnbSync -Config $script:Config -Now $script:Now.AddMinutes(5)
            $r2.To | Should -Be 'Account created'
            $req.Fields.OnbStatus | Should -Be 'Account created'
            $req.Fields.OnbObjectId | Should -Be $user.id
            $tasks = $script:World.Tasks($item.Id)
            $tasks.Count | Should -Be 7
            ($tasks | Where-Object { $_.Fields.OnbTaskKey -eq 'laptop' }).Fields.OnbDueDate | Should -Be '2026-12-02'

            $r3 = Invoke-OnbSync -Config $script:Config -Now $script:Now.AddMinutes(10)
            $r3 | Should -BeNullOrEmpty
            $script:World.Tasks($item.Id).Count | Should -Be 7
        }
        It 'reads every page of approved requests and sends them in one bulk request' {
            $script:World.PageSize = 1
            1..3 | ForEach-Object { $script:World.AddRequest((New-RequestFields -given "Person$_")) | Out-Null }
            $r = Invoke-OnbSync -Config $script:Config -Now $script:Now
            $r.Count | Should -Be 3
            ($script:World.Calls | Where-Object { $_ -like 'POST*bulkUpload' }).Count | Should -Be 1
            $script:World.Staged.Count | Should -Be 3
        }
        It 'splits more than 50 approved requests into several bulk requests' {
            1..53 | ForEach-Object { $script:World.AddRequest((New-RequestFields -given "Person$_")) | Out-Null }
            Invoke-OnbSync -Config $script:Config -Now $script:Now | Out-Null
            ($script:World.Calls | Where-Object { $_ -like 'POST*bulkUpload' }).Count | Should -Be 2
            $script:World.Staged.Count | Should -Be 53
        }
    }

    Describe 'Sign-in name conflicts' {
        It 'takes the next free name when another person already has it' {
            $script:World.AddUser(@{ userPrincipalName = 'joao.goncalves@contoso.com'; employeeId = 'E0001' }) | Out-Null
            $item = $script:World.AddRequest((New-RequestFields -given 'João' -surname 'Gonçalves'))
            Invoke-OnbSync -Config $script:Config -Now $script:Now | Out-Null
            $script:World.Request($item.Id).Fields.OnbUpn | Should -Be 'joao.goncalves2@contoso.com'
        }
        It 'keeps the existing name when the account already belongs to this request (a re-run)' {
            $item = $script:World.AddRequest((New-RequestFields))
            $script:World.AddUser(@{ userPrincipalName = 'casey.demo@contoso.com'; employeeId = 'NH00001'; accountEnabled = $false }) | Out-Null
            Invoke-OnbSync -Config $script:Config -Now $script:Now | Out-Null
            $script:World.Request($item.Id).Fields.OnbUpn | Should -Be 'casey.demo@contoso.com'
            $script:World.RunProvisioning()
            $script:World.ProvisioningLog | Should -Be @('Update NH00001: success')
            @($script:World.Users | Where-Object employeeId -eq 'NH00001').Count | Should -Be 1
        }
    }

    Describe 'Requests that must fail, clearly' {
        It 'fails when the manager has no employee ID (no bulk call at all)' {
            $item = $script:World.AddRequest((New-RequestFields -manager 'taylor.demo@contoso.com'))
            $r = Invoke-OnbSync -Config $script:Config -Now $script:Now
            $r.To | Should -Be 'Failed'
            $script:World.Request($item.Id).Fields.OnbMessage | Should -Match 'no employee ID'
            $script:World.Calls | Where-Object { $_ -like '*bulkUpload' } | Should -BeNullOrEmpty
        }
        It 'fails when the manager does not exist' {
            $item = $script:World.AddRequest((New-RequestFields -manager 'nobody@contoso.com'))
            Invoke-OnbSync -Config $script:Config -Now $script:Now | Out-Null
            $script:World.Request($item.Id).Fields.OnbMessage | Should -Match 'not found'
        }
        It 'fails a start date in the past and still sends the good ones' {
            $bad = $script:World.AddRequest((New-RequestFields -start '2026-11-20T00:00:00Z'))
            $good = $script:World.AddRequest((New-RequestFields -given 'Riley'))
            Invoke-OnbSync -Config $script:Config -Now $script:Now | Out-Null
            $script:World.Request($bad.Id).Fields.OnbStatus | Should -Be 'Failed'
            $script:World.Request($good.Id).Fields.OnbStatus | Should -Be 'Sent to Entra'
        }
        It 'marks the batch Failed when the provisioning API refuses it (403)' {
            $script:World.BulkStatus = 403
            $item = $script:World.AddRequest((New-RequestFields))
            Invoke-OnbSync -Config $script:Config -Now $script:Now | Out-Null
            $script:World.Request($item.Id).Fields.OnbStatus | Should -Be 'Failed'
            $script:World.Request($item.Id).Fields.OnbMessage | Should -Match 'HTTP 403'
        }
        It 'leaves requests Approved and throws on a server error, so the next run retries' {
            $script:World.BulkStatus = 503
            $item = $script:World.AddRequest((New-RequestFields))
            { Invoke-OnbSync -Config $script:Config -Now $script:Now } | Should -Throw '*stay Approved*'
            $script:World.Request($item.Id).Fields.OnbStatus | Should -Be 'Approved'
        }
    }

    Describe 'Concurrency and time-outs' {
        It 'does not overwrite an HR edit made while the run was working (412), and the retry creates one account' {
            $item = $script:World.AddRequest((New-RequestFields))
            $script:World.BeforePatch = { param($i) if ($i.Version -eq 1) { $i.Fields.OnbJobTitle = 'Senior sales representative'; $i.Version++ } }
            $r = Invoke-OnbSync -Config $script:Config -Now $script:Now
            $r.Outcome | Should -Be 'Conflict'
            $script:World.Request($item.Id).Fields.OnbStatus | Should -Be 'Approved'
            $script:World.Request($item.Id).Fields.OnbJobTitle | Should -Be 'Senior sales representative'

            $script:World.BeforePatch = $null
            (Invoke-OnbSync -Config $script:Config -Now $script:Now.AddMinutes(5)).Outcome | Should -Be 'Updated'
            $script:World.RunProvisioning()
            @($script:World.Users | Where-Object employeeId -eq 'NH00001').Count | Should -Be 1
            ($script:World.UserByEmployeeId('NH00001')).jobTitle | Should -Be 'Senior sales representative'
        }
        It 'waits for the account within the time-out, then fails with a pointer to the provisioning logs' {
            $f = New-RequestFields
            $f.OnbStatus = 'Sent to Entra'; $f.OnbEmployeeId = 'NH00001'; $f.OnbSentAt = '2026-11-23T09:50:00Z'
            $item = $script:World.AddRequest($f)
            Invoke-OnbSync -Config $script:Config -Now $script:Now | Should -BeNullOrEmpty
            $script:World.Request($item.Id).Fields.OnbStatus | Should -Be 'Sent to Entra'
            $r = Invoke-OnbSync -Config $script:Config -Now $script:Now.AddMinutes(60)
            $r.To | Should -Be 'Failed'
            $script:World.Request($item.Id).Fields.OnbMessage | Should -Match 'provisioning logs'
        }
        It 'reports a provisioning failure on a UPN taken after we checked as a time-out, not a second account' {
            $item = $script:World.AddRequest((New-RequestFields))
            Invoke-OnbSync -Config $script:Config -Now $script:Now | Out-Null
            $script:World.AddUser(@{ userPrincipalName = 'casey.demo@contoso.com'; employeeId = 'E9999' }) | Out-Null   # someone else, meanwhile
            $script:World.RunProvisioning()
            $script:World.ProvisioningLog[0] | Should -Match 'already exists'
            (Invoke-OnbSync -Config $script:Config -Now $script:Now.AddMinutes(61)).To | Should -Be 'Failed'
        }
    }

    Describe 'Function entry point' {
        BeforeAll {
            $script:SavedPath = $env:PSModulePath
            $env:PSModulePath = $script:ModulesDir + [System.IO.Path]::PathSeparator + $env:PSModulePath
        }
        AfterAll { $env:PSModulePath = $script:SavedPath }
        AfterEach { Get-ChildItem Env: | Where-Object Name -like 'Onboarding__*' | Remove-Item }

        It 'names every missing app setting' {
            { Get-OnbConfigFromEnvironment } | Should -Throw '*Onboarding__SiteId*Onboarding__UpnDomain*'
        }
        It 'run.ps1 reads its settings, syncs and logs one line per request' {
            $env:Onboarding__SiteId = $script:World.SiteId
            $env:Onboarding__RequestsListId = $script:World.RequestsListId
            $env:Onboarding__TasksListId = $script:World.TasksListId
            $env:Onboarding__ProvisioningServicePrincipalId = $script:World.SpId
            $env:Onboarding__ProvisioningJobId = $script:World.JobId
            $env:Onboarding__UpnDomain = 'contoso.com'
            $future = (Get-Date).Date.AddDays(14).ToString("yyyy-MM-dd'T'00:00:00'Z'")
            $script:World.AddRequest((New-RequestFields -start $future)) | Out-Null

            $out = & (Join-Path $PSScriptRoot '..' 'src' 'OnboardingSync' 'SyncOnboarding' 'run.ps1') -Timer ([pscustomobject]@{ IsPastDue = $false }) 6>&1
            ($out | Out-String) | Should -Match 'Request 1: Approved -> Sent to Entra \(Updated\)'
            ($out | Out-String) | Should -Match 'Sync finished: 1 item'
        }
    }
    AfterAll { Remove-Variable -Name OnbFakeWorld -Scope Global -ErrorAction SilentlyContinue }
}
