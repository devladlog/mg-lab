BeforeAll {
    $script:Module = Join-Path $PSScriptRoot '..' 'src' 'scripts' 'VendorRequest.psm1'
    Import-Module $script:Module -Force
    $script:Org = 'https://example.crm4.dynamics.com'
}

Describe 'table and column definitions' {
    It 'has an autonumber primary name column' {
        $t = Get-VendorRequestTableDefinition
        $p = $t.Attributes[0]
        $p.IsPrimaryName | Should -BeTrue
        $p.AutoNumberFormat | Should -Be 'VR-{SEQNUM:4}'
        $p.FormatName.Value | Should -Be 'Text'      # Learn: an autonumber column must have Text format
        $p.MaxLength | Should -BeGreaterThan 20      # room for VR-10000 and more (Learn: do not shrink MaxLength to the format)
        $t.SchemaName | Should -Be 'mgl_VendorRequest'
    }
    It 'serialises to JSON without errors' {
        { Get-VendorRequestTableDefinition | ConvertTo-Json -Depth 20 } | Should -Not -Throw
        { Get-VendorRequestColumnDefinitions | ConvertTo-Json -Depth 20 } | Should -Not -Throw
    }
    It 'defines the six columns the agent flow writes' {
        (Get-VendorRequestColumnDefinitions).SchemaName | Should -Be @(
            'mgl_VendorName', 'mgl_Category', 'mgl_EstimatedAnnualCost', 'mgl_Justification', 'mgl_ApprovalTier', 'mgl_Status')
    }
    It 'uses publisher-prefixed schema names and valid option values' {
        foreach ($c in Get-VendorRequestColumnDefinitions) { $c.SchemaName | Should -Match '^mgl_[A-Za-z]+$' }
        $cat = (Get-VendorRequestColumnDefinitions | Where-Object SchemaName -eq 'mgl_Category').OptionSet.Options
        $cat | Should -HaveCount 5
        ($cat | ForEach-Object { $_.Label.LocalizedLabels[0].Label }) | Should -Be @('Hosting', 'Printing', 'Travel', 'Security', 'Other')
        (($cat | ForEach-Object { $_.Value } | Sort-Object -Unique)) | Should -HaveCount 5
        $st = (Get-VendorRequestColumnDefinitions | Where-Object SchemaName -eq 'mgl_Status').OptionSet.Options
        ($st | ForEach-Object { $_.Label.LocalizedLabels[0].Label }) | Should -Be @('Submitted', 'Approved', 'Rejected')
    }
    It 'sets only LocalizedLabels in labels (UserLocalizedLabel is read-only)' {
        $l = (Get-VendorRequestTableDefinition).DisplayName
        $l.Keys | Should -Not -Contain 'UserLocalizedLabel'
        $l.LocalizedLabels[0].LanguageCode | Should -Be 1033
    }
    It 'money column takes its precision from the record currency, memo is a text area' {
        $m = Get-VendorRequestColumnDefinitions | Where-Object SchemaName -eq 'mgl_EstimatedAnnualCost'
        $m.PrecisionSource | Should -Be 2
        $memo = Get-VendorRequestColumnDefinitions | Where-Object SchemaName -eq 'mgl_Justification'
        $memo.Format | Should -Be 'TextArea'
    }
}

Describe 'Install-VendorRequestTable' {
    It 'creates the table then six columns, all inside the solution' {
        InModuleScope VendorRequest {
            $script:calls = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-RestMethod {
                $script:calls.Add(@{ Method = $Method; Uri = $Uri; Headers = $Headers; Body = $Body })
                if ($Method -eq 'GET') { throw [System.Exception]::new('Response status code does not indicate success: 404 (Not Found).') }
            }
            Install-VendorRequestTable -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken 'tok' -SolutionUniqueName 'MGLabVendorDesk' 6>$null
            $posts = @($script:calls | Where-Object { $_.Method -eq 'POST' })
            $posts | Should -HaveCount 7
            $posts[0].Uri | Should -Be 'https://example.crm4.dynamics.com/api/data/v9.2/EntityDefinitions'
            $posts[1].Uri | Should -Be "https://example.crm4.dynamics.com/api/data/v9.2/EntityDefinitions(LogicalName='mgl_vendorrequest')/Attributes"
            foreach ($p in $posts) {
                $p.Headers['MSCRM.SolutionUniqueName'] | Should -Be 'MGLabVendorDesk'
                $p.Headers['Authorization'] | Should -Be 'Bearer tok'
                $p.Headers['OData-Version'] | Should -Be '4.0'
                ($p.Body | ConvertFrom-Json).'@odata.type' | Should -Not -BeNullOrEmpty
            }
        }
    }
    It 'does nothing when the table already exists' {
        InModuleScope VendorRequest {
            $script:calls = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-RestMethod { $script:calls.Add($Method); @{ LogicalName = 'mgl_vendorrequest' } }
            Install-VendorRequestTable -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken 'tok' -SolutionUniqueName 'MGLabVendorDesk' 6>$null
            $script:calls | Should -Be @('GET')
        }
    }
    It 'rethrows errors that are not "table not found"' {
        InModuleScope VendorRequest {
            Mock Invoke-RestMethod { throw 'Response status code does not indicate success: 401 (Unauthorized).' }
            { Install-VendorRequestTable -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken 'bad' -SolutionUniqueName 'S' } |
                Should -Throw '*401*'
        }
    }
    It 'creates nothing with -WhatIf' {
        InModuleScope VendorRequest {
            $script:calls = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-RestMethod { $script:calls.Add($Method); if ($Method -eq 'GET') { throw '404 (Not Found)' } }
            Install-VendorRequestTable -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken 'tok' -SolutionUniqueName 'S' -WhatIf 6>$null
            @($script:calls | Where-Object { $_ -eq 'POST' }) | Should -HaveCount 0
        }
    }
    It 'accepts a SecureString token and the object returned by Get-AzAccessToken' {
        InModuleScope VendorRequest {
            $script:auth = @()
            Mock Invoke-RestMethod { $script:auth += $Headers['Authorization']; @{ value = @() } }
            $secure = ConvertTo-SecureString 'abc' -AsPlainText -Force
            Get-VendorRequest -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken $secure | Out-Null
            Get-VendorRequest -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken ([pscustomobject]@{ Token = $secure }) | Out-Null
            Get-VendorRequest -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken 'abc' | Out-Null
            $script:auth | Should -Be @('Bearer abc', 'Bearer abc', 'Bearer abc')
        }
    }
    It 'rejects an org URL that is not a Dataverse address' {
        { Install-VendorRequestTable -OrgUrl 'https://example.com' -AccessToken 't' -SolutionUniqueName 'S' } | Should -Throw '*OrgUrl*'
    }
    It 'rejects a solution name with spaces' {
        { Install-VendorRequestTable -OrgUrl $script:Org -AccessToken 't' -SolutionUniqueName 'My Solution' } | Should -Throw
    }
}

Describe 'Get-VendorRequest' {
    BeforeEach {
        InModuleScope VendorRequest {
            $script:last = $null
            Mock Invoke-RestMethod {
                $script:last = @{ Uri = $Uri; Headers = $Headers; Method = $Method }
                @{ value = @(
                    @{ mgl_requestnumber = 'VR-0002'; mgl_vendorname = 'Northwind Print'; mgl_approvaltier = 'Team lead'
                       'mgl_category@OData.Community.Display.V1.FormattedValue' = 'Printing'
                       'mgl_estimatedannualcost@OData.Community.Display.V1.FormattedValue' = '4,200.00'
                       'mgl_status@OData.Community.Display.V1.FormattedValue' = 'Submitted'; createdon = '2026-11-21T10:00:00Z' }
                ) }
            }
        }
    }
    It 'asks for the newest rows and the formatted values' {
        $rows = Get-VendorRequest -OrgUrl $script:Org -AccessToken 'tok' -Top 3
        InModuleScope VendorRequest {
            $script:last.Uri | Should -Match '/mgl_vendorrequests\?'
            $script:last.Uri | Should -Match '\$orderby=createdon desc'
            $script:last.Uri | Should -Match '\$top=3'
            $script:last.Uri | Should -Not -Match 'filter'
            $script:last.Headers['Prefer'] | Should -Be 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'
        }
        $rows[0].RequestNumber | Should -Be 'VR-0002'
        $rows[0].Category | Should -Be 'Printing'
        $rows[0].AnnualCost | Should -Be '4,200.00'
        $rows[0].Status | Should -Be 'Submitted'
    }
    It 'filters by request number' {
        Get-VendorRequest -OrgUrl $script:Org -AccessToken 'tok' -RequestNumber 'VR-0002' | Out-Null
        InModuleScope VendorRequest { $script:last.Uri | Should -Match "\`$filter=mgl_requestnumber eq 'VR-0002'" }
    }
    It 'refuses a request number that is not in the VR-0000 format (no injection through the filter)' {
        { Get-VendorRequest -OrgUrl $script:Org -AccessToken 't' -RequestNumber "x' or 1 eq 1 or 'y" } | Should -Throw
    }
    It 'doubles single quotes in OData strings' {
        ConvertTo-ODataString "O'Neil" | Should -Be "'O''Neil'"
    }
}

Describe 'Remove-VendorRequestTable' {
    It 'sends DELETE for the table, and nothing with -WhatIf' {
        InModuleScope VendorRequest {
            $script:calls = [System.Collections.Generic.List[object]]::new()
            Mock Invoke-RestMethod { $script:calls.Add(@{ Method = $Method; Uri = $Uri }) }
            Remove-VendorRequestTable -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken 't' -WhatIf
            $script:calls | Should -HaveCount 0
            Remove-VendorRequestTable -OrgUrl 'https://example.crm4.dynamics.com' -AccessToken 't' -Confirm:$false
            $script:calls | Should -HaveCount 1
            $script:calls[0].Method | Should -Be 'DELETE'
            $script:calls[0].Uri | Should -Be "https://example.crm4.dynamics.com/api/data/v9.2/EntityDefinitions(LogicalName='mgl_vendorrequest')"
        }
    }
}
