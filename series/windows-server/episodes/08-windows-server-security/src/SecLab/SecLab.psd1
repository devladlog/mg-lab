@{
    RootModule        = 'SecLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000008'
    Author            = 'DEVLADLOG'
    Description       = 'Security baseline check, remediation plan and Windows LAPS rollout for the DEVLADLOG lab.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @('Read-SecLabConfig', 'Get-SecCollectorScript', 'Get-SecFacts', 'Test-SecHost', 'ConvertTo-SecMarkdown',
        'Get-SecRemediationPlan', 'Get-SecRollbackPlan', 'Invoke-SecRemediation', 'Get-SecLapsPlan', 'Invoke-SecLapsPlan')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
