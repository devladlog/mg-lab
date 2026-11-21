@{
    # Source copy for tests. Install-OpsEndpoint generates the real manifest on the target with New-ModuleManifest.
    RootModule        = 'ContosoOps.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000050'
    Author            = 'DEVLADLOG'
    Description       = 'Functions exposed by the Contoso.AppOps JEA endpoint.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @('Get-OpsHealth', 'Clear-OpsLogFolder', 'Set-OpsSetting')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
