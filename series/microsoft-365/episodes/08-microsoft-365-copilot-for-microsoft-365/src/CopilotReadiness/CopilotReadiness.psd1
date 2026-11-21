@{
    RootModule        = 'CopilotReadiness.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000008'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft 365 Copilot readiness without a Copilot licence: tenant and per-user licence readiness, sensitivity label coverage, and an oversharing review of SharePoint and OneDrive sharing, all read-only through Microsoft Graph (DEVLADLOG Microsoft 365 #8).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-CopilotConfig', 'Get-CopilotSku', 'Get-CopilotUserLicence', 'Get-CopilotLabel', 'Get-CopilotDrive', 'Get-CopilotSharedItem',
        'Test-CopilotReadiness', 'Get-CopilotLabelFinding', 'Get-CopilotSharingFinding', 'Get-CopilotUsageReport',
        'ConvertTo-CopilotSnapshot', 'ConvertTo-CopilotMarkdown'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('Copilot', 'MicrosoftGraph', 'Readiness', 'Oversharing', 'SensitivityLabels') } }
}
