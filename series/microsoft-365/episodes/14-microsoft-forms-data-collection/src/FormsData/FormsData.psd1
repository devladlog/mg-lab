@{
    RootModule        = 'FormsData.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000014'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft Forms data collection as code: a SharePoint list provisioned from one JSON spec through Microsoft Graph (the destination of a Forms-triggered flow), the flow mapping, and a data-quality check and summary of the collected responses (DEVLADLOG Microsoft 365 #14).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-FDSpec', 'ConvertTo-FDColumn', 'Get-FDMetaColumn', 'ConvertTo-FDListBody', 'Get-FDFlowMap', 'Get-FDSiteId', 'Get-FDList',
        'Compare-FDColumn', 'Set-FDList', 'Get-FDResponse', 'Get-FDResponseFinding', 'Get-FDSummary', 'ConvertTo-FDMarkdown'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('MicrosoftForms', 'PowerAutomate', 'SharePoint', 'MicrosoftGraph') } }
}
