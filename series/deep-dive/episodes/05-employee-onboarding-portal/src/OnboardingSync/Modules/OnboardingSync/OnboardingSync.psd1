@{
    RootModule        = 'OnboardingSync.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000005'
    Author            = 'DEVLADLOG Deep Dive'
    Description       = 'Hands approved onboarding requests from SharePoint to Microsoft Entra API-driven inbound provisioning.'
    PowerShellVersion = '7.4'
    FunctionsToExport = @(
        'ConvertTo-OnbAsciiName', 'ConvertTo-OnbUpnAlias', 'Get-OnbUpnCandidates', 'Get-OnbEmployeeId',
        'ConvertTo-OnbLocalDate', 'ConvertTo-OnbUtc', 'ConvertTo-OnbHireDateTime', 'Test-OnbRequest', 'New-OnbScimOperation',
        'New-OnbScimBulkRequest', 'Get-OnbBusinessDay', 'New-OnbTaskPlan', 'Get-OnbAccessToken', 'Get-OnbRetryDelay',
        'Invoke-OnbGraph', 'Get-OnbListItems', 'Set-OnbRequestFields', 'Find-OnbUserByEmployeeId', 'Resolve-OnbUpn',
        'Get-OnbManagerEmployeeId', 'Send-OnbScimBulk', 'Add-OnbTasks', 'Get-OnbConfigFromEnvironment', 'Invoke-OnbSync'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
