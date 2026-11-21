#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# The provisioning tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong
# parameter name fails the test). They are skipped when PnP.PowerShell isn't installed.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
}

BeforeAll {
    $src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgListDesign.psm1') -Force
    $script:good = Import-MgListDesign -Path (Join-Path $src 'designs' 'purchase-requests.json')
    $script:bad = Import-MgListDesign -Path (Join-Path $src 'designs' 'bad-design.json')

    function New-TestList([hashtable]$Overrides = @{}) {
        $l = [ordered]@{
            title = 'T'; template = 'GenericList'; expectedItems = 100
            versioning = [pscustomobject]@{ enabled = $true; majorVersions = 500 }
            fields = @([pscustomobject]@{ internalName = 'Status'; type = 'Choice'; indexed = $true; choices = @('A') })
            views = @()
        }
        foreach ($k in $Overrides.Keys) { $l[$k] = $Overrides[$k] }
        [pscustomobject]@{ lists = @([pscustomobject]$l) }
    }
    function Rules($design) { @(Test-MgListDesign -Design $design | ForEach-Object Rule) }
}

Describe 'Test-MgListDesign' {
    It 'passes the purchase-requests design with no findings' {
        @(Test-MgListDesign -Design $good) | Should -HaveCount 0
    }

    It 'finds every planted problem in the bad design' {
        $r = Rules $bad
        foreach ($rule in 'LD002', 'LD003', 'LD004', 'LD005', 'LD006', 'LD007', 'LD008', 'LD009', 'LD010', 'LD011', 'LD012', 'LD013', 'LD014') {
            $r | Should -Contain $rule
        }
        $r | Should -HaveCount 13
    }

    It 'the audit-demo design provisions cleanly but breaks exactly two view rules' {
        $demo = Import-MgListDesign -Path (Join-Path $PSScriptRoot '..' 'src' 'designs' 'audit-demo.json')
        (Rules $demo | Sort-Object) | Should -Be @('LD012', 'LD013')
        foreach ($f in $demo.lists[0].fields) { { [xml](ConvertTo-MgFieldXml -Field $f) } | Should -Not -Throw }
    }

    It 'flags a list beyond 30 million items' {
        Rules (New-TestList @{ expectedItems = 30000001 }) | Should -Contain 'LD001'
    }

    It 'a 5,000-item list may have an unfiltered view; 5,001 may not' {
        $v = @([pscustomobject]@{ title = 'All'; fields = @('Title') })
        Rules (New-TestList @{ expectedItems = 5000; views = $v }) | Should -Not -Contain 'LD012'
        Rules (New-TestList @{ expectedItems = 5001; views = $v }) | Should -Contain 'LD012'
    }

    It 'a filter that returns 5,000 rows is fine; 5,001 is not' {
        $mk = { param($n) @([pscustomobject]@{ title = 'V'; fields = @('Title'); expectedRows = $n
                    filters = @([pscustomobject]@{ field = 'Status'; op = 'Eq'; value = 'A' }) }) }
        Rules (New-TestList @{ views = (& $mk 5000) }) | Should -Not -Contain 'LD011'
        Rules (New-TestList @{ views = (& $mk 5001) }) | Should -Contain 'LD011'
    }

    It 'counts Created By and Modified By towards the 12 lookup columns' {
        $people = 1..10 | ForEach-Object { [pscustomobject]@{ internalName = "P$_"; type = 'User' } }
        $fields = @($people) + [pscustomobject]@{ internalName = 'Status'; type = 'Choice'; indexed = $true; choices = @('A') }
        $twelve = @([pscustomobject]@{ title = 'V'; fields = @($people.internalName) + 'Author' + 'Editor' })
        $thirteen = @([pscustomobject]@{ title = 'V'; fields = @($people.internalName) + 'Author' + 'Editor' + 'Title' })
        Rules (New-TestList @{ fields = $fields; views = $twelve }) | Should -Not -Contain 'LD010'
        $fields += [pscustomobject]@{ internalName = 'L1'; type = 'Lookup' }
        $thirteen[0].fields = @($thirteen[0].fields) + 'L1'
        Rules (New-TestList @{ fields = $fields; views = $thirteen }) | Should -Contain 'LD010'
    }

    It 'requires the first filter of a large list to be on an indexed, non-lookup column' {
        $fields = @(
            [pscustomobject]@{ internalName = 'Status'; type = 'Choice'; indexed = $true; choices = @('A') }
            [pscustomobject]@{ internalName = 'Amount'; type = 'Currency' }
            [pscustomobject]@{ internalName = 'Vendor'; type = 'Lookup'; indexed = $true }
        )
        $view = { param($first) @([pscustomobject]@{ title = 'V'; fields = @('Title')
                    filters = @([pscustomobject]@{ field = $first; op = 'Eq'; value = 'x' }
                                [pscustomobject]@{ field = 'Status'; op = 'Eq'; value = 'A' }) }) }
        Rules (New-TestList @{ expectedItems = 60000; fields = $fields; views = (& $view 'Status') }) | Should -HaveCount 0
        Rules (New-TestList @{ expectedItems = 60000; fields = $fields; views = (& $view 'Amount') }) | Should -Contain 'LD013'
        Rules (New-TestList @{ expectedItems = 60000; fields = $fields; views = (& $view 'Vendor') }) | Should -Contain 'LD014'
    }

    It 'breaking inheritance is allowed at 100,000 items, not above' {
        Rules (New-TestList @{ expectedItems = 100000; breakInheritance = $true }) | Should -Not -Contain 'LD006'
        Rules (New-TestList @{ expectedItems = 100001; breakInheritance = $true }) | Should -Contain 'LD006'
    }

    It 'unique scopes: 5,000 ok, above is a warning, above 50,000 an error' {
        @(Test-MgListDesign (New-TestList @{ plannedUniqueScopes = 5000 })) | Should -HaveCount 0
        (Test-MgListDesign (New-TestList @{ plannedUniqueScopes = 5001 })).Severity | Should -Be 'Warning'
        (Test-MgListDesign (New-TestList @{ plannedUniqueScopes = 50001 })).Severity | Should -Be 'Error'
    }

    It 'versioning off is an error on a library and a warning on a list' {
        $off = [pscustomobject]@{ enabled = $false }
        (Test-MgListDesign (New-TestList @{ versioning = $off })).Severity | Should -Be 'Warning'
        (Test-MgListDesign (New-TestList @{ versioning = $off; template = 'DocumentLibrary' })).Severity | Should -Be 'Error'
    }

    It 'automatic version limits are not checked against the 100-version minimum' {
        $auto = [pscustomobject]@{ enabled = $true; automatic = $true; majorVersions = 10 }
        Rules (New-TestList @{ versioning = $auto }) | Should -Not -Contain 'LD005'
    }

    It 'warns about internal names that SharePoint would encode, but not about built-in columns' {
        $fields = @(
            [pscustomobject]@{ internalName = 'Due Date'; type = 'DateTime' }
            [pscustomobject]@{ internalName = '_ModerationStatus'; type = 'ModStat'; builtIn = $true }
        )
        $f = @(Test-MgListDesign (New-TestList @{ fields = $fields }))
        $f | Should -HaveCount 1
        $f[0].Message | Should -Match 'Due_x0020_Date'
    }
}

Describe 'ConvertTo-MgFieldXml' {
    It 'builds a choice column with choices, default, index and a clean internal name' {
        $f = $good.lists[0].fields | Where-Object internalName -eq 'RequestStatus'
        [xml]$x = ConvertTo-MgFieldXml -Field $f
        $x.Field.Type | Should -Be 'Choice'
        $x.Field.Name | Should -Be 'RequestStatus'
        $x.Field.StaticName | Should -Be 'RequestStatus'
        $x.Field.DisplayName | Should -Be 'Status'
        $x.Field.Indexed | Should -Be 'TRUE'
        $x.Field.Required | Should -Be 'TRUE'
        @($x.Field.CHOICES.CHOICE) | Should -HaveCount 5
        $x.Field.Default | Should -Be 'New'
    }

    It 'escapes XML characters in names and choices' {
        $f = [pscustomobject]@{ internalName = 'Terms'; displayName = 'Terms & <conditions>'; type = 'Choice'; choices = @('A & B') }
        [xml]$x = ConvertTo-MgFieldXml -Field $f
        $x.Field.DisplayName | Should -Be 'Terms & <conditions>'
        $x.Field.CHOICES.CHOICE | Should -Be 'A & B'
    }

    It 'date-only, person and multi-person columns' {
        ([xml](ConvertTo-MgFieldXml ([pscustomobject]@{ internalName = 'D'; type = 'DateTime'; dateOnly = $true }))).Field.Format | Should -Be 'DateOnly'
        ([xml](ConvertTo-MgFieldXml ([pscustomobject]@{ internalName = 'P'; type = 'User' }))).Field.UserSelectionMode | Should -Be 'PeopleOnly'
        ([xml](ConvertTo-MgFieldXml ([pscustomobject]@{ internalName = 'M'; type = 'UserMulti' }))).Field.Mult | Should -Be 'TRUE'
    }

    It 'a lookup needs the target list id' {
        $f = [pscustomobject]@{ internalName = 'Vendor'; type = 'Lookup'; lookupList = 'Vendors' }
        { ConvertTo-MgFieldXml -Field $f } | Should -Throw '*LookupListId*'
        ([xml](ConvertTo-MgFieldXml -Field $f -LookupListId '00000000-0000-0000-0000-000000000000')).Field.List |
            Should -Be '{00000000-0000-0000-0000-000000000000}'
    }

    It 'rejects types it does not know' {
        { ConvertTo-MgFieldXml ([pscustomobject]@{ internalName = 'X'; type = 'Geolocation' }) } | Should -Throw '*Unsupported*'
    }
}

Describe 'ConvertTo-MgViewQuery' {
    BeforeAll {
        $script:types = @{ RequestStatus = 'Choice'; Requester = 'User'; DueDate = 'DateTime'; Amount = 'Currency' }
    }

    It 'single filter and order by' {
        $v = $good.lists[0].views[0]
        ConvertTo-MgViewQuery -View $v -FieldTypes $types |
            Should -Be "<Where><Neq><FieldRef Name='RequestStatus' /><Value Type='Choice'>Closed</Value></Neq></Where><OrderBy><FieldRef Name='DueDate' Ascending='TRUE' /></OrderBy>"
    }

    It '[Me] becomes the current user id and [Today+7] an offset' {
        $q1 = ConvertTo-MgViewQuery -View $good.lists[0].views[1] -FieldTypes $types
        $q1 | Should -Match "<Eq><FieldRef Name='Requester' /><Value Type='Integer'><UserID Type='Integer' /></Value></Eq>"
        $q2 = ConvertTo-MgViewQuery -View $good.lists[0].views[2] -FieldTypes $types
        $q2 | Should -Match "<Today OffsetDays='7' />"
        $neg = [pscustomobject]@{ title = 'x'; filters = @([pscustomobject]@{ field = 'DueDate'; op = 'Lt'; value = '[Today-3]' }) }
        ConvertTo-MgViewQuery -View $neg -FieldTypes $types | Should -Match "OffsetDays='-3'"
    }

    It 'nests three filters with And, keeping the first filter first' {
        $v = [pscustomobject]@{ title = 'x'; filters = @(
                [pscustomobject]@{ field = 'RequestStatus'; op = 'Eq'; value = 'New' }
                [pscustomobject]@{ field = 'Amount'; op = 'Gt'; value = '1000' }
                [pscustomobject]@{ field = 'DueDate'; op = 'IsNotNull' }) }
        $q = ConvertTo-MgViewQuery -View $v -FieldTypes $types
        [xml]$doc = "<Query>$q</Query>"
        @($doc.SelectNodes('//And')) | Should -HaveCount 2
        @($doc.SelectNodes('//FieldRef') | ForEach-Object Name) | Should -Be @('RequestStatus', 'Amount', 'DueDate')
    }

    It 'round-trips through the CAML parser used by the audit' {
        InModuleScope MgListDesign -Parameters @{ v = $good.lists[0].views[2]; t = $types } {
            param($v, $t)
            $f = @(Get-MgCamlFilters (ConvertTo-MgViewQuery -View $v -FieldTypes $t))
            $f.field | Should -Be @('DueDate', 'RequestStatus')
            $f.op | Should -Be @('Leq', 'Neq')
        }
    }

    It 'rejects unknown operators' {
        $v = [pscustomobject]@{ title = 'x'; filters = @([pscustomobject]@{ field = 'Amount'; op = 'Between'; value = '1' }) }
        { ConvertTo-MgViewQuery -View $v } | Should -Throw '*Between*'
    }
}

Describe 'ConvertTo-MgListDesign (audit of a live list)' {
    It 'lints what is in the tenant for the size it will grow to' {
        $list = [pscustomobject]@{ Title = 'Legacy'; ItemCount = 1200; BaseTemplate = 100; EnableVersioning = $true; MajorVersionLimit = 500; HasUniqueRoleAssignments = $false }
        $fields = @(
            [pscustomobject]@{ InternalName = 'Title'; Title = 'Title'; TypeAsString = 'Text'; Indexed = $false; Hidden = $false; FromBaseType = $true }
            [pscustomobject]@{ InternalName = 'Modified'; Title = 'Modified'; TypeAsString = 'DateTime'; Indexed = $true; Hidden = $false; FromBaseType = $true }
            [pscustomobject]@{ InternalName = '_ModerationStatus'; Title = 'Approval Status'; TypeAsString = 'ModStat'; Indexed = $false; Hidden = $true; FromBaseType = $true }
            [pscustomobject]@{ InternalName = 'Amount'; Title = 'Amount'; TypeAsString = 'Currency'; Indexed = $false; Hidden = $false; FromBaseType = $false }
        )
        $views = @(
            [pscustomobject]@{ Title = 'Recent'; ViewFields = @('LinkTitle', 'Modified'); RowLimit = 30; Hidden = $false
                ViewQuery = "<Where><Geq><FieldRef Name='Modified' /><Value Type='DateTime'><Today OffsetDays='-30' /></Value></Geq></Where>" }
            [pscustomobject]@{ Title = 'Big'; ViewFields = @('LinkTitle', 'Amount'); RowLimit = 30; Hidden = $false
                ViewQuery = "<Where><Gt><FieldRef Name='Amount' /><Value Type='Currency'>1000</Value></Gt></Where>" }
        )
        $now = ConvertTo-MgListDesign -List $list -Fields $fields -Views $views
        $now.lists[0].expectedItems | Should -Be 1200
        @(Test-MgListDesign $now) | Should -HaveCount 0

        $later = ConvertTo-MgListDesign -List $list -Fields $fields -Views $views -ExpectedItems 60000
        $f = @(Test-MgListDesign $later)
        $f | Should -HaveCount 1
        $f[0].Rule | Should -Be 'LD013'
        $f[0].Target | Should -Be 'Legacy / Big'
    }
}

Describe 'New-MgSampleRequest' {
    It 'is deterministic and only uses values the design allows' {
        $a = @(New-MgSampleRequest -Count 25 -RequesterEmail 'alex.demo@contoso.com' -Today ([datetime]'2026-12-01'))
        $b = @(New-MgSampleRequest -Count 25 -RequesterEmail 'alex.demo@contoso.com' -Today ([datetime]'2026-12-01'))
        $a | Should -HaveCount 25
        ($a | ConvertTo-Json) | Should -Be ($b | ConvertTo-Json)
        $choices = @{}
        foreach ($f in $good.lists[0].fields | Where-Object type -eq 'Choice') { $choices[$f.internalName] = $f.choices }
        foreach ($row in $a) {
            $choices.RequestStatus | Should -Contain $row.RequestStatus
            $choices.Department | Should -Contain $row.Department
            $row.Amount | Should -BeGreaterThan 0
        }
    }
}

Describe 'Invoke-MgListProvisioning (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
    }

    It 'creates lists, columns, versioning and views on an empty site' {
        Mock -ModuleName MgListDesign Get-PnPList { $null }
        Mock -ModuleName MgListDesign New-PnPList { [pscustomobject]@{ Title = $Title } }
        Mock -ModuleName MgListDesign Set-PnPList { }
        Mock -ModuleName MgListDesign Get-PnPField { $null }
        Mock -ModuleName MgListDesign Add-PnPFieldFromXml { }
        Mock -ModuleName MgListDesign Get-PnPView { $null }
        Mock -ModuleName MgListDesign Add-PnPView { }

        $log = @(Invoke-MgListProvisioning -Design $good -Confirm:$false)

        Should -Invoke -ModuleName MgListDesign New-PnPList -Times 2 -Exactly
        Should -Invoke -ModuleName MgListDesign New-PnPList -Times 1 -Exactly -ParameterFilter { $Template -eq 'DocumentLibrary' -and $Url -eq 'Contracts' }
        Should -Invoke -ModuleName MgListDesign Set-PnPList -Times 1 -Exactly -ParameterFilter { $MajorVersions -eq 100 }
        Should -Invoke -ModuleName MgListDesign Set-PnPList -Times 1 -Exactly -ParameterFilter { $EnableAutoExpirationVersionTrim -eq $true }
        Should -Invoke -ModuleName MgListDesign Add-PnPFieldFromXml -Times 10 -Exactly
        Should -Invoke -ModuleName MgListDesign Add-PnPFieldFromXml -Times 1 -Exactly -ParameterFilter { $FieldXml -match 'Name="DueDate"' -and $FieldXml -match 'Indexed="TRUE"' }
        Should -Invoke -ModuleName MgListDesign Add-PnPView -Times 5 -Exactly
        Should -Invoke -ModuleName MgListDesign Add-PnPView -Times 2 -Exactly -ParameterFilter { $SetAsDefault }
        ($log | Group-Object Action | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Count)" }) -join ',' |
            Should -Be 'AddField=10,AddView=5,CreateList=2,SetVersioning=2'
    }

    It 'is idempotent: only adds the missing index and updates existing views' {
        Mock -ModuleName MgListDesign Get-PnPList { [pscustomobject]@{ Title = $Identity } }
        Mock -ModuleName MgListDesign New-PnPList { throw 'should not create' }
        Mock -ModuleName MgListDesign Set-PnPList { }
        Mock -ModuleName MgListDesign Get-PnPField { [pscustomobject]@{ InternalName = $Identity.Name; Indexed = ($Identity.Name -ne 'DueDate') } }
        Mock -ModuleName MgListDesign Add-PnPFieldFromXml { throw 'should not add' }
        Mock -ModuleName MgListDesign Set-PnPField { }
        Mock -ModuleName MgListDesign Get-PnPView { [pscustomobject]@{ Title = $Identity.Title } }
        Mock -ModuleName MgListDesign Set-PnPView { }
        Mock -ModuleName MgListDesign Remove-PnPView { }

        $log = @(Invoke-MgListProvisioning -Design $good -Confirm:$false)
        Should -Invoke -ModuleName MgListDesign Remove-PnPView -Times 1 -Exactly -ParameterFilter { $Identity.Title -eq 'All Items' -and $Force }
        Should -Invoke -ModuleName MgListDesign Remove-PnPView -Times 1 -Exactly -ParameterFilter { $Identity.Title -eq 'All Documents' }

        Should -Invoke -ModuleName MgListDesign Set-PnPField -Times 1 -Exactly -ParameterFilter { $Identity.Name -eq 'DueDate' -and $Values.Indexed -eq $true }
        Should -Invoke -ModuleName MgListDesign Set-PnPView -Times 5 -Exactly
        @($log | Where-Object Action -eq 'IndexField') | Should -HaveCount 1
    }

    It '-WhatIf changes nothing but still reports the plan' {
        Mock -ModuleName MgListDesign Get-PnPList { $null }
        Mock -ModuleName MgListDesign New-PnPList { throw 'WhatIf violated' }
        Mock -ModuleName MgListDesign Set-PnPList { throw 'WhatIf violated' }
        Mock -ModuleName MgListDesign Get-PnPField { $null }
        Mock -ModuleName MgListDesign Add-PnPFieldFromXml { throw 'WhatIf violated' }
        Mock -ModuleName MgListDesign Get-PnPView { $null }
        Mock -ModuleName MgListDesign Add-PnPView { throw 'WhatIf violated' }

        $log = @(Invoke-MgListProvisioning -Design $good -WhatIf)
        $log | Should -HaveCount 19
    }

    It 'Get-MgListAudit reads the list with the properties it needs' {
        Mock -ModuleName MgListDesign Get-PnPList {
            [pscustomobject]@{ Title = 'Purchase Requests'; ItemCount = 40; BaseTemplate = 100; EnableVersioning = $true; MajorVersionLimit = 100; HasUniqueRoleAssignments = $false }
        }
        Mock -ModuleName MgListDesign Get-PnPField {
            [pscustomobject]@{ InternalName = 'Title'; Title = 'Title'; TypeAsString = 'Text'; Indexed = $false; Hidden = $false; FromBaseType = $true }
            [pscustomobject]@{ InternalName = 'RequestStatus'; Title = 'Status'; TypeAsString = 'Choice'; Indexed = $true; Hidden = $false; FromBaseType = $false }
        }
        Mock -ModuleName MgListDesign Get-PnPView {
            [pscustomobject]@{ Title = 'Open requests'; ViewFields = @('LinkTitle', 'RequestStatus'); RowLimit = 100; Hidden = $false
                ViewQuery = "<Where><Neq><FieldRef Name='RequestStatus' /><Value Type='Choice'>Closed</Value></Neq></Where>" }
        }
        $a = Get-MgListAudit -ListTitle 'Purchase Requests' -ExpectedItems 60000
        $a.Design.lists[0].expectedItems | Should -Be 60000
        $a.Findings | Should -HaveCount 0
        Should -Invoke -ModuleName MgListDesign Get-PnPList -ParameterFilter { $Includes -contains 'MajorVersionLimit' }
    }
}

Describe 'Invoke-ListDesign.ps1' {
    It 'parses without errors' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..' 'src' 'Invoke-ListDesign.ps1'), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -HaveCount 0
    }

    It 'lints a design without touching a tenant' {
        $out = & (Join-Path $PSScriptRoot '..' 'src' 'Invoke-ListDesign.ps1') -DesignPath (Join-Path $PSScriptRoot '..' 'src' 'designs' 'purchase-requests.json') 6>&1
        ($out -join "`n") | Should -Match 'No findings'
    }
}
