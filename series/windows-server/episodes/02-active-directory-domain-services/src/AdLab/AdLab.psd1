@{
    RootModule        = 'AdLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000000'
    Author            = 'Momento Galatico'
    Description       = 'DEVLADLOG Windows Server #2: idempotent OU/user provisioning from CSV and an Active Directory hygiene report.'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'ConvertTo-AdLabAscii', 'ConvertTo-AdLabSamAccountName', 'Get-AdLabUniqueSamAccountName', 'Get-AdLabOuPlan',
        'New-AdLabUserPlan', 'ConvertFrom-AdLabFileTime', 'Test-AdLabHygiene', 'ConvertTo-AdLabMarkdown',
        'Invoke-AdLabProvisioning', 'Export-AdLabSnapshot'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
