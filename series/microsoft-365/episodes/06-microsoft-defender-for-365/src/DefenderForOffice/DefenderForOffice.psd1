@{
    RootModule        = 'DefenderForOffice.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000006'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft Defender for Office 365 as code: preset security policy assignment, real coverage per mailbox, configuration analyzer drift, EmailEvents hunting and attack simulation results (DEVLADLOG Microsoft 365 #6).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-DefenderConfig', 'ConvertTo-DOPresetRuleParameter', 'Test-DORecipientInScope', 'Get-DOProtectionCoverage',
        'Get-DefenderFinding', 'ConvertTo-DefenderMarkdown', 'New-DOHuntingQuery', 'ConvertFrom-DOHuntingResult',
        'Get-DOSimulationSummary', 'Get-DefenderInventory', 'Set-DefenderPresetPolicy', 'Invoke-DOHuntingQuery',
        'Get-DOAttackSimulationReport'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('DefenderForOffice365', 'ExchangeOnline', 'PresetSecurityPolicies', 'AdvancedHunting', 'AttackSimulation', 'MicrosoftGraph') } }
}
