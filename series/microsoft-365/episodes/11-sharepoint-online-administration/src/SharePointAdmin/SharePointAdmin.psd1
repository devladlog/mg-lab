@{
    RootModule        = 'SharePointAdmin.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000011'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'SharePoint Online administration through Microsoft Graph: tenant settings against a baseline, site hygiene from the usage report (inactive, near quota, no owner, empty), and a guarded remediation with a rollback file (DEVLADLOG Microsoft 365 #11).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-SPABaseline', 'Get-SPATenantSetting', 'Get-SPASiteUsageReport', 'Get-SPAReportPrivacy',
        'Get-SPASettingFinding', 'Test-SPAConcealedReport', 'Get-SPASiteRow', 'Get-SPASiteFinding', 'Get-SPAStorageSummary',
        'Get-SPARemediationPlan', 'Invoke-SPARemediation', 'Restore-SPARemediation', 'ConvertTo-SPAMarkdown'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('SharePoint', 'MicrosoftGraph', 'Governance', 'Baseline') } }
}
