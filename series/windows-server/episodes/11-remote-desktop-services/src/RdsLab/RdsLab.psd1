@{
    RootModule        = 'RdsLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000011'
    Author            = 'DEVLADLOG'
    Description       = 'Remote Desktop Services health check, deployment plan and session report for the DEVLADLOG lab.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @('Read-RdsLabConfig', 'Get-RdsCollectorScript', 'Get-RdsFacts', 'Test-RdsDeployment', 'Get-RdsSessionSummary',
        'ConvertTo-RdsMarkdown', 'Get-RdsDeploymentPlan', 'Invoke-RdsDeploymentPlan', 'Invoke-RdsDisconnectedLogoff')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
