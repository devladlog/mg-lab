@{
    RootModule        = 'IntuneDevices.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000007'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft Intune as code: a Windows compliance policy (settings, actions for noncompliance, assignment) kept in sync with one JSON file, a managed-device audit (noncompliant, stale, unencrypted, old OS, duplicates) and a device sync, all through Microsoft Graph (DEVLADLOG Microsoft 365 #7).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-IntuneConfig', 'ConvertTo-IDCompliancePolicyBody', 'ConvertTo-IDAssignmentBody', 'Compare-IntuneCompliancePolicy',
        'Get-IntuneCompliancePolicy', 'Set-IntuneCompliancePolicy', 'Get-IntuneManagedDevice', 'Get-IntuneDeviceFinding',
        'Get-IntuneComplianceSummary', 'ConvertTo-IntuneMarkdown', 'Invoke-IntuneDeviceSync'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('Intune', 'MicrosoftGraph', 'DeviceCompliance', 'Windows11', 'EndpointManagement') } }
}
