#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }

BeforeAll {
    $script:root = Split-Path -Parent $PSScriptRoot
    $script:manifest = Join-Path $root 'src/ContosoRequests/ContosoRequests.psd1'
    $script:csv = Join-Path $root 'samples/requests.csv'
    $script:approvers = Join-Path $root 'samples/approvers.json'
    Import-Module $manifest -Force
}

Describe 'Module' {
    It 'has a valid manifest that needs PowerShell 7.6 (the version we tested on)' {
        $info = Test-ModuleManifest -Path $manifest
        $info.PowerShellVersion | Should -Be ([version] '7.6')
    }

    It 'exports exactly the three public functions and keeps the helpers private' {
        $exported = (Get-Module ContosoRequests).ExportedFunctions.Keys | Sort-Object
        $exported | Should -Be @('Export-ContosoApprovalPack', 'Get-ContosoApprovalRoute', 'Import-ContosoRequest')
        Get-Command -Module ContosoRequests -Name 'Get-ContosoPriority' -ErrorAction SilentlyContinue | Should -BeNullOrEmpty
    }

    It 'advertises -WhatIf and -Confirm only on the function that changes something' {
        (Get-Command Export-ContosoApprovalPack).Parameters.Keys | Should -Contain 'WhatIf'
        (Get-Command Import-ContosoRequest).Parameters.Keys | Should -Not -Contain 'WhatIf'
    }
}

Describe 'Get-ContosoPriority' {
    It 'uses >= at both boundaries: <budget> is <expected>' -ForEach @(
        @{ budget = 49999.99; expected = 'Normal' }
        @{ budget = 50000; expected = 'High' }
        @{ budget = 249999.99; expected = 'High' }
        @{ budget = 250000; expected = 'Board' }
    ) {
        InModuleScope ContosoRequests -Parameters @{ budget = $budget } {
            Get-ContosoPriority -Budget $budget
        } | Should -Be $expected
    }
}

Describe 'Import-ContosoRequest' {
    BeforeAll {
        $script:requests = @(Import-ContosoRequest -Path $csv -ErrorVariable script:rejected -ErrorAction SilentlyContinue)
    }

    It 'returns the 9 valid rows as typed objects' {
        $requests.Count | Should -Be 9
        $requests | ForEach-Object { $_.PSObject.TypeNames[0] | Should -Be 'Contoso.Request' }
        $requests[0].Budget | Should -BeOfType [decimal]
        $requests[0].Submitted | Should -BeOfType [datetime]
    }

    It 'reports exactly the 4 bad rows, in order, with a stable error id and the row number' {
        $rejected.Count | Should -Be 4
        $rejected.FullyQualifiedErrorId -replace ',.*$' | Should -Be @(
            'ContosoRequest.InvalidBudget', 'ContosoRequest.InvalidBudget',
            'ContosoRequest.InvalidCode', 'ContosoRequest.InvalidDate')
        $rejected[0].ErrorDetails.Message | Should -BeLike 'requests.csv row 9: PR-2026-0308*'
        $rejected[0].TargetObject.code | Should -Be 'PR-2026-0308'
    }

    It 'puts the exact boundary budget 50000 in High (series rule, same as episode 6)' {
        ($requests | Where-Object Code -eq 'PR-2026-0303').Priority | Should -Be 'High'
        ($requests | Where-Object Code -eq 'PR-2026-0302').Priority | Should -Be 'Normal'
    }

    It 'reads "75,000" with the invariant culture' {
        ($requests | Where-Object Code -eq 'PR-2026-0306').Budget | Should -Be 75000
    }

    It 'is not fooled by the machine culture (German decimal comma)' {
        $previous = [cultureinfo]::CurrentCulture
        try {
            [cultureinfo]::CurrentCulture = [cultureinfo]::new('de-DE')
            $again = @(Import-ContosoRequest -Path $csv -ErrorAction SilentlyContinue)
        }
        finally {
            [cultureinfo]::CurrentCulture = $previous
        }
        $again.Count | Should -Be 9
        ($again | Where-Object Code -eq 'PR-2026-0302').Budget | Should -Be 49999.99
    }

    It 'does not throw by default: try/catch never sees a bad row' {
        { Import-ContosoRequest -Path $csv -ErrorAction SilentlyContinue } | Should -Not -Throw
    }

    It 'stops at the first bad row with -ErrorAction Stop' {
        { Import-ContosoRequest -Path $csv -ErrorAction Stop } | Should -Throw -ErrorId 'ContosoRequest.InvalidBudget*'
    }

    It 'binds files from the pipeline by property name (Get-ChildItem -> FullName)' {
        $viaPipeline = @(Get-ChildItem -Path $csv | Import-ContosoRequest -ErrorAction SilentlyContinue)
        $viaPipeline.Count | Should -Be 9
    }

    It 'rejects a missing file at parameter binding, before any work' {
        { Import-ContosoRequest -Path (Join-Path $TestDrive 'nope.csv') } |
            Should -Throw -ExpectedMessage '*Cannot find the CSV file*'
    }
}

Describe 'Get-ContosoApprovalRoute' {
    BeforeAll {
        $script:requests = @(Import-ContosoRequest -Path $csv -ErrorAction SilentlyContinue)
        $script:routes = @($requests | Get-ContosoApprovalRoute -ApproverPath $approvers -ErrorVariable script:routeErrors -ErrorAction SilentlyContinue)
    }

    It 'routes 8 requests and rejects the one with a department that is not in the file' {
        $routes.Count | Should -Be 8
        $routeErrors.Count | Should -Be 1
        $routeErrors[0].FullyQualifiedErrorId | Should -BeLike 'ContosoRequest.UnknownDepartment*'
        $routeErrors[0].Exception.Message | Should -BeLike 'PR-2026-0311*Legal*'
    }

    It 'adds approvers by priority: Normal = 1, High = 2, Board = 3' {
        $byCode = $routes | Group-Object { $_.Request.Code } -AsHashTable -AsString
        $byCode['PR-2026-0301'][0].Approvers.Role | Should -Be @('Manager')
        $byCode['PR-2026-0303'][0].Approvers.Role | Should -Be @('Manager', 'Finance')
        $byCode['PR-2026-0304'][0].Approvers.Name | Should -Be @('Alex Demo', 'Sam Demo', 'Taylor Demo')
    }

    It 'uses the spelling from the approvers file: "it" becomes "IT"' {
        ($routes | Where-Object { $_.Request.Code -eq 'PR-2026-0306' }).Department | Should -Be 'IT'
    }

    It 'refuses objects that are not Contoso.Request' {
        { [pscustomobject]@{ Code = 'x' } | Get-ContosoApprovalRoute -ApproverPath $approvers } |
            Should -Throw -ExpectedMessage '*Contoso.Request*'
    }

    It 'stops when the approvers file itself is broken (that is not one row''s problem)' {
        $broken = Join-Path $TestDrive 'broken.json'
        Set-Content -LiteralPath $broken -Value '{ not json'
        { $requests | Get-ContosoApprovalRoute -ApproverPath $broken } | Should -Throw
    }
}

Describe 'Export-ContosoApprovalPack' {
    BeforeEach {
        $script:out = Join-Path $TestDrive ('out-' + [guid]::NewGuid().ToString('N'))
        $script:routes = Import-ContosoRequest -Path $csv -ErrorAction SilentlyContinue |
            Get-ContosoApprovalRoute -ApproverPath $approvers -ErrorAction SilentlyContinue
    }

    It '-WhatIf writes nothing and creates no folders (host output is read from a child pwsh)' {
        # The "What if:" lines go straight to the host, so a child process is the only way to capture them.
        $command = "Import-Module '$manifest'; Import-ContosoRequest '$csv' -ErrorAction SilentlyContinue | " +
        "Get-ContosoApprovalRoute -ApproverPath '$approvers' -ErrorAction SilentlyContinue | " +
        "Export-ContosoApprovalPack -Destination '$out' -WhatIf"
        $lines = @(pwsh -NoProfile -Command $command)
        $lines.Count | Should -Be 8
        $lines[0] | Should -BeLike 'What if: Performing the operation "Write approval pack" on target "*PR-2026-0301.json".'
        Test-Path -LiteralPath $out | Should -BeFalse
    }

    It 'writes one file per request under <Destination>/<Department>/<Code>.json' {
        $packs = @($routes | Export-ContosoApprovalPack -Destination $out -PassThru)
        $packs.Count | Should -Be 8
        (Get-ChildItem -Path $out -Recurse -File).Count | Should -Be 8
        Join-Path $out 'IT/PR-2026-0306.json' | Should -Exist
        (Get-ChildItem -Path $out -Directory).Name | Sort-Object | Should -Be @('HR', 'IT', 'Marketing', 'Operations')
    }

    It 'keeps every approver in the JSON (-Depth is set explicitly)' {
        $routes | Export-ContosoApprovalPack -Destination $out
        $pack = Get-Content -LiteralPath (Join-Path $out 'IT/PR-2026-0304.json') -Raw | ConvertFrom-Json
        $pack.request.budget | Should -Be 300000
        $pack.route.priority | Should -Be 'Board'
        $pack.route.approvers.name | Should -Be @('Alex Demo', 'Sam Demo', 'Taylor Demo')
    }

    It 'writes UTF-8 without a byte order mark' {
        $routes | Export-ContosoApprovalPack -Destination $out
        $bytes = [System.IO.File]::ReadAllBytes((Join-Path $out 'IT/PR-2026-0301.json'))
        $bytes[0] | Should -Be ([byte][char] '{')
    }

    It 'is safe to run twice: existing packs are not overwritten without -Force' {
        $routes | Export-ContosoApprovalPack -Destination $out
        $file = Join-Path $out 'IT/PR-2026-0301.json'
        Set-Content -LiteralPath $file -Value 'edited by a human'

        $routes | Export-ContosoApprovalPack -Destination $out -ErrorVariable again -ErrorAction SilentlyContinue
        $again.Count | Should -Be 8
        $again[0].FullyQualifiedErrorId | Should -BeLike 'ContosoPack.AlreadyExists*'
        (Get-Content -LiteralPath $file -Raw).Trim() | Should -Be 'edited by a human'

        $routes | Export-ContosoApprovalPack -Destination $out -Force
        (Get-Content -LiteralPath $file -Raw) | Should -BeLike '*PR-2026-0301*'
    }

    It 'refuses objects that are not Contoso.ApprovalRoute' {
        { [pscustomobject]@{ Request = 1 } | Export-ContosoApprovalPack -Destination $out } |
            Should -Throw -ExpectedMessage '*Contoso.ApprovalRoute*'
    }
}
