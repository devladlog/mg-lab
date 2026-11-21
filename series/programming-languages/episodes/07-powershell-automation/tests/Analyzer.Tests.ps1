#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.0.0' }, PSScriptAnalyzer

BeforeAll {
    $script:root = Split-Path -Parent $PSScriptRoot
    $script:settings = Join-Path $root 'PSScriptAnalyzerSettings.psd1'
}

Describe 'PSScriptAnalyzer gate' {
    It 'finds nothing at Warning or Error in the module and in build.ps1' {
        $findings = @(Invoke-ScriptAnalyzer -Path (Join-Path $root 'src') -Recurse -Settings $settings) +
        @(Invoke-ScriptAnalyzer -Path (Join-Path $root 'build.ps1') -Settings $settings)
        $findings | ForEach-Object { "$($_.ScriptName):$($_.Line) $($_.RuleName)" } | Should -BeNullOrEmpty
    }

    It 'fails the legacy demo script on the rules we talk about in the video' {
        $findings = Invoke-ScriptAnalyzer -Path (Join-Path $root 'demo/bad-script.ps1') -Settings $settings
        $findings.Count | Should -Be 13
        ($findings | Where-Object Severity -eq 'Error').RuleName | Should -Be 'PSAvoidUsingConvertToSecureStringWithPlainText'
        $findings.RuleName | Should -Contain 'PSAvoidUsingWriteHost'
        $findings.RuleName | Should -Contain 'PSAvoidUsingInvokeExpression'
        $findings.RuleName | Should -Contain 'PSAvoidUsingEmptyCatchBlock'
        $findings.RuleName | Should -Contain 'PSAvoidUsingCmdletAliases'
        $findings.RuleName | Should -Contain 'PSUseApprovedVerbs'
        $findings.RuleName | Should -Contain 'PSAvoidUsingPlainTextForPassword'
    }
}
