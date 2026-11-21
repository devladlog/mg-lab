@{
    RootModule        = 'CertLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000009'
    Author            = 'DEVLADLOG'
    Description       = 'AD CS health check (certificates, CA, templates), renewal plan and CA build plan for the DEVLADLOG lab.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @('Read-CertLabConfig', 'Get-CertCollectorScript', 'Get-CaCollectorScript', 'Get-CertFacts', 'Get-CertTemplateName', 'Test-CertHost',
        'Test-CaTemplate', 'Test-CaFacts', 'ConvertTo-CertMarkdown', 'Get-CertRenewalPlan', 'Invoke-CertRenewal', 'Get-CertCaPlan', 'Invoke-CertCaPlan')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
