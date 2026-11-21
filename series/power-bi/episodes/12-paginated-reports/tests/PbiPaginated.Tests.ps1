# Pester 5+: PbiPaginated module. Invoke-PowerBIRestMethod is mocked with responses shaped like the Learn samples
# (tests/fixtures/rest: zero GUIDs, fictional names). These tests prove the requests we build, not the service.
#   pwsh -NoProfile -Command "Invoke-Pester ./tests -Output Detailed"

BeforeAll {
    if (-not (Get-Command Invoke-PowerBIRestMethod -ErrorAction SilentlyContinue)) {
        function global:Invoke-PowerBIRestMethod { param($Url, $Method, $Body, $InFile, $ContentType, $OutFile) throw 'not mocked' }
    }
    $script:Root = Join-Path $PSScriptRoot '..' 'src' 'ps'
    Import-Module (Join-Path $script:Root 'PbiPaginated' 'PbiPaginated.psd1') -Force
    $script:Fx = Join-Path $PSScriptRoot 'fixtures' 'rest'
    $global:PbiFx = $script:Fx
    $script:Ws = '00000000-0000-0000-0000-0000000000a1'
    $script:Rep = '00000000-0000-0000-0000-0000000000c1'
    function script:Fixture([string] $n) { Get-Content -Raw (Join-Path $script:Fx $n) }
    $global:PbiCalls = [System.Collections.Generic.List[object]]::new()
    $global:PbiQueue = @{}
}

Describe 'New-PbiMultipartFile' {
    It 'wraps the file bytes in one form-data part with the file name' {
        $src = Join-Path $TestDrive 'x.rdl'; [IO.File]::WriteAllBytes($src, [byte[]](60, 82, 101, 112, 111, 114, 116, 62))
        $r = New-PbiMultipartFile -Path $src -OutFile (Join-Path $TestDrive 'body.bin') -Boundary 'BND'
        $r.ContentType | Should -Be 'multipart/form-data; boundary=BND'
        $text = [Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($r.Path))
        $text | Should -Be "--BND`r`nContent-Disposition: form-data; name=`"file0`"; filename=`"x.rdl`"`r`nContent-Type: application/octet-stream`r`n`r`n<Report>`r`n--BND--`r`n"
    }
    It 'throws for a missing file' { { New-PbiMultipartFile -Path (Join-Path $TestDrive 'no.rdl') -OutFile (Join-Path $TestDrive 'o') } | Should -Throw '*not found*' }
}

Describe 'New-PbiExportRequest' {
    It 'builds the body of Export To File for a paginated report' {
        $b = New-PbiExportRequest -Format PDF -Parameter @{ Year = 2025 } -Username 'alex.demo@contoso.example' -DatasetId '00000000-0000-0000-0000-0000000000e1'
        $j = $b | ConvertTo-Json -Depth 8 | ConvertFrom-Json
        $j.format | Should -Be 'PDF'
        $j.paginatedReportConfiguration.parameterValues[0].name | Should -Be 'Year'
        $j.paginatedReportConfiguration.parameterValues[0].value | Should -BeOfType [string]
        $j.paginatedReportConfiguration.parameterValues[0].value | Should -Be '2025'
        $j.paginatedReportConfiguration.identities[0].username | Should -Be 'alex.demo@contoso.example'
        $j.paginatedReportConfiguration.identities[0].datasets[0] | Should -Be '00000000-0000-0000-0000-0000000000e1'
    }
    It 'has no configuration when there is nothing to configure' { (New-PbiExportRequest -Format XLSX).Keys | Should -Be @('format') }
    It 'refuses PNG, which is for Power BI reports only' { { New-PbiExportRequest -Format PNG } | Should -Throw }
}

Describe 'Import-PbiRdl' {
    BeforeEach {
        $global:PbiCalls.Clear()
        $global:PbiQueue = @{ imports = [System.Collections.Generic.Queue[string]]::new() }
        Mock -ModuleName PbiPaginated Start-Sleep {}
        Mock -ModuleName PbiPaginated Invoke-PowerBIRestMethod {
            $global:PbiCalls.Add(@{ Method = $Method; Url = $Url; InFile = $InFile; ContentType = $ContentType; Size = $(if ($InFile) { (Get-Item $InFile).Length }) })
            if ($Method -eq 'Post') { return Get-Content -Raw (Join-Path $global:PbiFx 'import-started.json') }
            $f = $global:PbiQueue.imports.Dequeue()
            Get-Content -Raw (Join-Path $global:PbiFx $f)
        }
        $script:rdl = Join-Path $TestDrive 'ContosoStoreStatement.rdl'
        Copy-Item (Join-Path $PSScriptRoot '..' 'src' 'report' 'ContosoStoreStatement.rdl') $script:rdl
    }
    It 'posts the file with the extension in datasetDisplayName and waits until Succeeded' {
        'import-publishing.json', 'import-ok.json' | ForEach-Object { $global:PbiQueue.imports.Enqueue($_) }
        $r = Import-PbiRdl -WorkspaceId $script:Ws -Path $script:rdl -NameConflict Overwrite -IntervalSeconds 1
        $r.reports[0].reportType | Should -Be 'PaginatedReport'
        $post = $global:PbiCalls[0]
        $post.Method | Should -Be 'Post'
        $post.Url | Should -Be "groups/$($script:Ws)/imports?datasetDisplayName=ContosoStoreStatement.rdl&nameConflict=Overwrite"
        $post.ContentType | Should -BeLike 'multipart/form-data; boundary=*'
        $post.Size | Should -BeGreaterThan (Get-Item $script:rdl).Length
        $global:PbiCalls.Count | Should -Be 3
        $global:PbiCalls[2].Url | Should -Be "groups/$($script:Ws)/imports/00000000-0000-0000-0000-0000000000b1"
    }
    It 'adds .rdl to a name without it' {
        $global:PbiQueue.imports.Enqueue('import-ok.json')
        Import-PbiRdl -WorkspaceId $script:Ws -Path $script:rdl -Name 'Store statement' -IntervalSeconds 0 | Out-Null
        $global:PbiCalls[0].Url | Should -Be "groups/$($script:Ws)/imports?datasetDisplayName=Store%20statement.rdl&nameConflict=Abort"
    }
    It 'throws with the error code when the import fails' {
        $global:PbiQueue.imports.Enqueue('import-failed.json')
        { Import-PbiRdl -WorkspaceId $script:Ws -Path $script:rdl -IntervalSeconds 0 } | Should -Throw '*InvalidReportDefinition*'
    }
    It 'sends nothing with -WhatIf' {
        $r = Import-PbiRdl -WorkspaceId $script:Ws -Path $script:rdl -WhatIf
        $r.Sent | Should -BeFalse
        $global:PbiCalls.Count | Should -Be 0
    }
    It 'refuses anything but .rdl and Ignore-style conflict modes' {
        { Import-PbiRdl -WorkspaceId $script:Ws -Path (Join-Path $TestDrive 'a.pbix') } | Should -Throw '*Not an .rdl*'
        { Import-PbiRdl -WorkspaceId $script:Ws -Path $script:rdl -NameConflict Ignore } | Should -Throw
    }
}

Describe 'Export-PbiPaginatedReport' {
    BeforeEach {
        $global:PbiCalls.Clear()
        $global:PbiQueue = @{ status = [System.Collections.Generic.Queue[string]]::new() }
        Mock -ModuleName PbiPaginated Start-Sleep {}
        Mock -ModuleName PbiPaginated Invoke-PowerBIRestMethod {
            $global:PbiCalls.Add(@{ Method = $Method; Url = $Url; Body = $Body; OutFile = $OutFile })
            $dir = $global:PbiFx
            if ($Method -eq 'Post') { return Get-Content -Raw (Join-Path $dir 'export-started.json') }
            if ($OutFile) { [IO.File]::WriteAllBytes($OutFile, [byte[]](37, 80, 68, 70)); return }
            Get-Content -Raw (Join-Path $dir ($global:PbiQueue.status.Dequeue()))
        }
        $script:out = Join-Path $TestDrive 'statement-2025.pdf'
    }
    It 'starts, polls until Succeeded, then downloads the file' {
        'export-running.json', 'export-running.json', 'export-ok.json' | ForEach-Object { $global:PbiQueue.status.Enqueue($_) }
        $f = Export-PbiPaginatedReport -WorkspaceId $script:Ws -ReportId $script:Rep -OutFile $script:out -Parameter @{ Year = 2025 } -Username 'alex.demo@contoso.example' -IntervalSeconds 1
        $f.FullName | Should -Be $script:out
        (Test-Path $script:out) | Should -BeTrue
        $global:PbiCalls.Count | Should -Be 5
        $global:PbiCalls[0].Url | Should -Be "groups/$($script:Ws)/reports/$($script:Rep)/ExportTo"
        ($global:PbiCalls[0].Body | ConvertFrom-Json).paginatedReportConfiguration.parameterValues[0].value | Should -Be '2025'
        $global:PbiCalls[1].Url | Should -Be "groups/$($script:Ws)/reports/$($script:Rep)/exports/00000000-0000-0000-0000-0000000000d1"
        $global:PbiCalls[4].Url | Should -BeLike '*/exports/00000000-0000-0000-0000-0000000000d1/file'
    }
    It 'throws when the export fails' {
        $global:PbiQueue.status.Enqueue('export-failed.json')
        $never = Join-Path $TestDrive 'never.pdf'
        { Export-PbiPaginatedReport -WorkspaceId $script:Ws -ReportId $script:Rep -OutFile $never -IntervalSeconds 0 } | Should -Throw '*failed*'
        (Test-Path $never) | Should -BeFalse
    }
    It 'times out when the export keeps running' {
        1..50 | ForEach-Object { $global:PbiQueue.status.Enqueue('export-running.json') }
        { Wait-PbiExport -WorkspaceId $script:Ws -ReportId $script:Rep -ExportId 'x' -TimeoutSeconds 0 -IntervalSeconds 0 } | Should -Throw '*did not finish*40 %*'
    }
    It 'sends nothing with -WhatIf' {
        Export-PbiPaginatedReport -WorkspaceId $script:Ws -ReportId $script:Rep -OutFile $script:out -WhatIf | Should -BeNullOrEmpty
        $global:PbiCalls.Count | Should -Be 0
    }
}

Describe 'Invoke-StatementRun.ps1 -WhatIf' {
    It 'lists the files it would write and sends nothing' {
        $global:PbiCalls.Clear()
        Mock -ModuleName PbiPaginated Invoke-PowerBIRestMethod { $global:PbiCalls.Add(@{ Url = $Url }); throw 'must not be called' }
        $r = @(& (Join-Path $script:Root 'Invoke-StatementRun.ps1') -WorkspaceId $script:Ws -ReportId $script:Rep -Year 2024, 2025 -OutDir (Join-Path $TestDrive 'o') -WhatIf 6>$null)
        $r.Count | Should -Be 2
        $r[0].File | Should -BeLike '*statement-2024.pdf'
        $r[1].File | Should -BeLike '*statement-2025.pdf'
        $r.Status | Should -Be @('whatif', 'whatif')
        $global:PbiCalls.Count | Should -Be 0
    }
}
