@{
    RootModule        = 'PurviewCompliance.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000005'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft Purview as code on Security & Compliance PowerShell: sensitivity labels, DLP in simulation, retention labels, plan/deploy with a real WhatIf, audit (DEVLADLOG Microsoft 365 #5).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-PurviewConfig', 'ConvertTo-PVLabelParameter', 'ConvertTo-PVLabelPolicyParameter', 'ConvertTo-PVDlpPolicyParameter',
        'ConvertTo-PVSensitiveInfoCondition', 'ConvertTo-PVDlpRuleParameter', 'ConvertTo-PVRetentionLabelParameter',
        'ConvertTo-PVRetentionPolicyParameter', 'ConvertTo-PVRetentionRuleParameter', 'Get-PurviewPlan', 'Get-PurviewFinding',
        'ConvertTo-PurviewMarkdown', 'Test-PVLuhn', 'New-DlpTestContent', 'Get-PurviewInventory', 'Invoke-PurviewPlan',
        'Set-PurviewDlpMode'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('Purview', 'DLP', 'SensitivityLabels', 'Retention', 'Compliance', 'SecurityAndCompliance') } }
}
