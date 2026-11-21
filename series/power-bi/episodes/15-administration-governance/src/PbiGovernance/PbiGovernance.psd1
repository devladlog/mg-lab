@{
    RootModule        = 'PbiGovernance.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000015'
    Author            = 'MG Lab'
    Description       = 'Power BI / Fabric governance checks over the admin APIs: activity log, metadata scanner, orphaned workspaces, tenant settings drift (DEVLADLOG Power BI #15).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @('Get-PbiGovernanceRule', 'Get-PbiActivityEvent', 'Get-PbiActivitySummary', 'Get-PbiOrphanedWorkspace',
        'Get-PbiModifiedWorkspace', 'Invoke-PbiWorkspaceScan', 'Test-PbiGovernance',
        'Get-PbiTenantSetting', 'Export-PbiTenantBaseline', 'Compare-PbiTenantSetting', 'New-PbiGovernanceReport')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ ExternalModuleDependencies = @('MicrosoftPowerBIMgmt') } }
}
