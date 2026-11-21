@{
    RootModule        = 'OpsLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000005'
    Author            = 'DEVLADLOG'
    Description       = 'JEA endpoint from a JSON definition (lint, merge, register) and an unattended runbook that only uses it.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @(
        'Read-OpsEndpointDefinition', 'Merge-OpsRoleCapability', 'Test-OpsEndpointDefinition', 'ConvertTo-OpsLintMarkdown',
        'ConvertTo-OpsRoleCapabilityParams', 'ConvertTo-OpsSessionConfigParams', 'Install-OpsEndpoint', 'Get-OpsModuleFunction',
        'Read-OpsJobConfig', 'Get-OpsRetryDelay', 'Invoke-OpsWithRetry', 'Get-OpsRecentRestart', 'Get-OpsDecision', 'Write-OpsLog',
        'Connect-OpsTarget', 'Disconnect-OpsTarget', 'Invoke-OpsRemote', 'Invoke-OpsMaintenanceRun'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
