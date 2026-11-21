@{
    RootModule        = 'ServerBaseline.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000000'
    Author            = 'Momento Galatico'
    Description       = 'DEVLADLOG Windows Server #1: collect a snapshot from Windows Server over PowerShell remoting and check it against a baseline.'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-SbCollectorScript', 'ConvertTo-SbSnapshot', 'Get-SbSnapshot', 'Test-SbBaseline',
        'New-SbUnreachableFinding', 'Format-SbFindingOrder', 'ConvertTo-SbMarkdown'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
