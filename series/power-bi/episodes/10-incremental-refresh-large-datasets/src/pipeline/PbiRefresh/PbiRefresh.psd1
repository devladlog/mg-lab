@{
    RootModule        = 'PbiRefresh.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000010'
    Author            = 'MG Lab'
    Description       = 'Enhanced refresh through the Power BI REST API: partitions, refresh policy, effective date, wait and cancel (DEVLADLOG Power BI #10).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @('New-PbiRefreshRequest', 'Start-PbiEnhancedRefresh', 'Get-PbiRefresh', 'Wait-PbiRefresh', 'Stop-PbiRefresh')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ ExternalModuleDependencies = @('MicrosoftPowerBIMgmt') } }
}
