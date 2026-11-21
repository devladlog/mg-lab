@{
    RootModule        = 'LicensingOptimization.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000009'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft 365 licence optimization through Microsoft Graph: who holds a licence they do not use (disabled, inactive, never signed in), redundant and duplicate assignments, assignment errors, idle seats and what they cost, plus a guarded reclaim with a rollback file (DEVLADLOG Microsoft 365 #9).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-LOConfig', 'Get-LOSku', 'Get-LOUser', 'Get-LOProtectedUserId',
        'Get-LOLicenceFinding', 'Get-LOSeatSummary', 'Get-LOSavingSummary',
        'Get-LOReclaimPlan', 'Invoke-LOReclaim', 'Restore-LOReclaim', 'ConvertTo-LOMarkdown'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('Licensing', 'MicrosoftGraph', 'Optimization', 'Entra') } }
}
