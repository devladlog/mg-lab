@{
    RootModule        = 'CoreLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000010'
    Author            = 'DEVLADLOG'
    Description       = 'Server Core footprint and readiness check, setup plan for Core servers, and a Nano Server container image check for the DEVLADLOG lab.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @('Read-CoreLabConfig', 'Get-CoreCollectorScript', 'Get-CoreFacts', 'Get-CoreInstallType', 'Test-CoreHost', 'Get-CoreFootprint',
        'Test-NanoDockerfile', 'ConvertTo-CoreMarkdown', 'Get-CoreSetupPlan', 'Invoke-CoreSetupPlan')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
