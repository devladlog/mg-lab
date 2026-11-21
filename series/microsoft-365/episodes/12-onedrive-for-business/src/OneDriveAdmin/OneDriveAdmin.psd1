@{
    RootModule        = 'OneDriveAdmin.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000012'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'OneDrive for Business administration: tenant OneDrive settings against a baseline and an account audit from Microsoft Graph (read-only), plus the sync-app policies (silent sign-in, Files On-Demand, Known Folder Move) written to a Windows PC with a rollback file (DEVLADLOG Microsoft 365 #12).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-ODABaseline', 'Get-ODATenantSetting', 'Get-ODAUsageReport', 'Get-ODAReportPrivacy',
        'Get-ODASettingFinding', 'Test-ODAConcealedReport', 'Get-ODAAccountRow', 'Get-ODAAccountFinding', 'Get-ODAStorageSummary',
        'Get-ODASyncPolicyPlan', 'Get-ODASyncPolicyState', 'Set-ODASyncPolicy', 'Restore-ODASyncPolicy', 'ConvertTo-ODAMarkdown'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('OneDrive', 'MicrosoftGraph', 'KnownFolderMove', 'FilesOnDemand') } }
}
