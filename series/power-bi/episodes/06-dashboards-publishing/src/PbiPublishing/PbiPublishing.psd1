@{
    RootModule        = 'PbiPublishing.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000006'
    Author            = 'MG Lab'
    Description       = 'Publishing checks and dashboard automation for Power BI (DEVLADLOG Power BI #6).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @('Get-PbiPublishingRule', 'Test-PbipPublishReadiness', 'Get-PbiWorkspaceInventory',
                          'Test-PbiWorkspacePublishing', 'Copy-PbiDashboard')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ ExternalModuleDependencies = @('MicrosoftPowerBIMgmt') } }
}
