@{
    RootModule        = 'GpoLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000000'
    Author            = 'Momento Galatico'
    Description       = 'DEVLADLOG Windows Server #3: Group Policy as code (idempotent deployment), snapshot export, hygiene report and backups.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @(
        'Get-GpoLabScope', 'Test-GpoLabHalfEnabled', 'Read-GpoLabDefinition', 'Test-GpoLabHygiene', 'ConvertTo-GpoLabMarkdown',
        'Invoke-GpoLabDeployment', 'Export-GpoLabSnapshot', 'Backup-GpoLab'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
