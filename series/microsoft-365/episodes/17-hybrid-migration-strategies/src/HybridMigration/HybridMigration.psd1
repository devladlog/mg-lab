@{
    RootModule        = 'HybridMigration.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000017'
    Author            = 'DEVLADLOG'
    Description       = 'Hybrid migration planning: pick the Exchange migration path, check Active Directory before directory synchronization, plan dependency-safe migration waves, fix UPN suffixes with a rollback file.'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-HMConfig', 'Get-HMMailboxInventory', 'Get-HMStrategy', 'Get-HMDirectoryInventory', 'Get-HMDirectoryFinding', 'Get-HMSummary',
        'New-HMWavePlan', 'Export-HMWaveCsv', 'Get-HMBatchCommand', 'ConvertTo-HMMarkdown',
        'Get-HMUpnFixPlan', 'Invoke-HMUpnFix', 'Restore-HMUpn'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
