@{
    RootModule        = 'VivaEngage.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000016'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Viva Engage communities and roles as code on Microsoft Graph: config, diff, create with async polling, audit (DEVLADLOG Microsoft 365 #16).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-VivaCommunityConfig', 'ConvertTo-VivaCommunityBody', 'ConvertTo-VivaGroupRefBody', 'Get-VivaHeaderValue',
        'Get-VivaCommunityDiff', 'Get-VivaFinding', 'ConvertTo-VivaMarkdown',
        'Invoke-VivaRequest', 'Wait-VivaOperation', 'New-VivaCommunity', 'Get-VivaInventory', 'Set-VivaCommunity'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('Microsoft365', 'Viva', 'VivaEngage', 'MicrosoftGraph') } }
}
