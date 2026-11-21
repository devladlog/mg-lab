@{
    RootModule        = 'PbiShared.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000007'
    Author            = 'MG Lab'
    Description       = 'Audit and wiring for shared semantic models and dataflows (DEVLADLOG Power BI #7).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @('Get-PbiSharedModelRule', 'Get-PbiSharedModelInventory', 'Test-PbiSharedModel', 'Set-PbiModelParameter')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ ExternalModuleDependencies = @('MicrosoftPowerBIMgmt') } }
}
