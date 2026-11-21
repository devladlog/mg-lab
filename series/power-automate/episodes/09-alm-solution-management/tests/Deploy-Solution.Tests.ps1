# Pester tests for scripts/Deploy-Solution.ps1 with a stand-in `pac` that records its arguments.
# Run: pwsh -NoProfile -Command "Invoke-Pester tests/Deploy-Solution.Tests.ps1 -Output Detailed"
BeforeAll {
    $script:Root = Split-Path $PSScriptRoot -Parent
    $script:Script = Join-Path $Root 'src/scripts/Deploy-Solution.ps1'
    $script:Solution = Join-Path $Root 'src/solution'
    $script:Log = Join-Path $TestDrive 'pac.log'
    # A stand-in pac written in PowerShell, so the same test runs on Windows and Linux.
    $script:FakePac = Join-Path $TestDrive 'pac.ps1'
    @'
Add-Content -LiteralPath $env:FAKE_PAC_LOG -Value ($args -join ' ')
$cmd = "$($args[0]) $($args[1])"
if ($cmd -eq 'solution pack') {
    for ($i = 0; $i -lt $args.Count - 1; $i++) { if ($args[$i] -eq '--zipfile') { New-Item -ItemType File -Force -Path $args[$i + 1] | Out-Null } }
}
if ($env:FAKE_PAC_FAIL -and $cmd -eq $env:FAKE_PAC_FAIL) { [Console]::Error.WriteLine('boom'); exit 3 }
exit 0
'@ | Set-Content -LiteralPath $FakePac
    $script:Good = Join-Path $TestDrive 'settings.json'
    '{ "EnvironmentVariables": [], "ConnectionReferences": [] }' | Set-Content $Good
    $env:FAKE_PAC_LOG = $Log
}
Describe 'Deploy-Solution' {
    BeforeEach {
        Remove-Item $Log -ErrorAction SilentlyContinue
        $env:FAKE_PAC_FAIL = $null
        $env:PAC_CLIENT_SECRET = $null
    }
    It 'packs managed, then imports with the settings file and activates flows' {
        & $Script -SolutionFolder $Solution -SettingsFile $Good -EnvironmentUrl 'https://test.example' -Pac $FakePac -OutputFolder (Join-Path $TestDrive 'o') | Out-Null
        $lines = Get-Content $Log
        $lines.Count | Should -Be 2
        $lines[0] | Should -Match '^solution pack --zipfile .*ITRequestNotices_managed\.zip --folder .* --packagetype Managed$'
        $lines[1] | Should -Match '^solution import --path .*ITRequestNotices_managed\.zip --environment https://test\.example --settings-file .*settings\.json --activate-plugins --publish-changes --async'
    }
    It 'Upgrade (the default) adds --stage-and-upgrade' {
        & $Script -SolutionFolder $Solution -SettingsFile $Good -EnvironmentUrl 'https://test.example' -Pac $FakePac -OutputFolder (Join-Path $TestDrive 'o') | Out-Null
        (Get-Content $Log)[1] | Should -Match '--stage-and-upgrade'
    }
    It 'Update does not' {
        & $Script -SolutionFolder $Solution -SettingsFile $Good -EnvironmentUrl 'https://test.example' -Mode Update -Pac $FakePac -OutputFolder (Join-Path $TestDrive 'o') | Out-Null
        (Get-Content $Log)[1] | Should -Not -Match 'upgrade'
    }
    It 'refuses a settings file that still has tokens, before it calls pac at all' {
        $bad = Join-Path $TestDrive 'bad.json'
        '{ "ConnectionReferences": [ { "ConnectionId": "${CONN_SHAREPOINT}" } ] }' | Set-Content $bad
        { & $Script -SolutionFolder $Solution -SettingsFile $bad -EnvironmentUrl 'https://t' -Pac $FakePac } | Should -Throw '*unresolved tokens: ${CONN_SHAREPOINT}*'
        Test-Path $Log | Should -BeFalse
    }
    It 'stops when the folder is not a solution' {
        { & $Script -SolutionFolder $TestDrive -SettingsFile $Good -EnvironmentUrl 'https://t' -Pac $FakePac } | Should -Throw '*Not an unpacked solution*'
    }
    It 'does not import when the pack fails' {
        $env:FAKE_PAC_FAIL = 'solution pack'
        { & $Script -SolutionFolder $Solution -SettingsFile $Good -EnvironmentUrl 'https://t' -Pac $FakePac -OutputFolder (Join-Path $TestDrive 'o') } | Should -Throw '*pac solution pack failed with exit code 3*'
        (Get-Content $Log).Count | Should -Be 1
    }
    It 'fails when the import fails' {
        $env:FAKE_PAC_FAIL = 'solution import'
        { & $Script -SolutionFolder $Solution -SettingsFile $Good -EnvironmentUrl 'https://t' -Pac $FakePac -OutputFolder (Join-Path $TestDrive 'o') } | Should -Throw '*pac solution import failed*'
    }
    It 'signs in as the service principal first when the secret is in the environment, and never prints it' {
        $env:PAC_CLIENT_SECRET = 's3cret-value'; $env:PAC_APPLICATION_ID = '00000000-0000-0000-0000-000000000001'; $env:PAC_TENANT_ID = '00000000-0000-0000-0000-000000000002'
        $out = & $Script -SolutionFolder $Solution -SettingsFile $Good -EnvironmentUrl 'https://t' -Pac $FakePac -OutputFolder (Join-Path $TestDrive 'o') *>&1 | Out-String
        $lines = Get-Content $Log
        $lines[0] | Should -Match '^auth create --applicationId 00000000-0000-0000-0000-000000000001 --clientSecret s3cret-value --tenant .* --environment https://t$'
        $lines.Count | Should -Be 3
        $out | Should -Not -Match 's3cret-value'
        $env:PAC_CLIENT_SECRET = $null
    }
}
