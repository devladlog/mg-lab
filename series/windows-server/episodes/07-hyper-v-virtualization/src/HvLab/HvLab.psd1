@{
    RootModule        = 'HvLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000007'
    Author            = 'DEVLADLOG'
    Description       = 'Hyper-V host audit, throwaway VM builder, checkpoint cleanup and tear-down for the lab.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @(
        'Read-HvLabConfig', 'Get-HvCollectorScript', 'Get-HvHostFacts', 'Test-HvHost', 'ConvertTo-HvMarkdown',
        'Get-HvChainDepth', 'Get-HvVmPlan', 'New-HvLabVm', 'Get-HvCheckpointPlan', 'Wait-HvDiskMerge',
        'Invoke-HvCheckpointCleanup', 'Remove-HvLabVm'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
