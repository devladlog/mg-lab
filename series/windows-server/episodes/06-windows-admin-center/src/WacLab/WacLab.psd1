@{
    RootModule        = 'WacLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000006'
    Author            = 'DEVLADLOG'
    Description       = 'Windows Admin Center gateway for the lab: preflight, silent install, connections CSV, Kerberos SSO (RBCD), RBAC checks.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @(
        'Read-WacLabConfig', 'ConvertTo-WacConnectionCsv', 'Test-WacConnectionCsv', 'Find-WacPowerShellModule', 'Import-WacLabConnection',
        'Get-WacGatewayUrl', 'Get-WacCollectorScript', 'Get-WacGatewayFacts', 'Test-WacGateway', 'ConvertTo-WacMarkdown',
        'Get-WacInstallerArgument', 'Install-WacGateway', 'Get-WacDelegationPlan', 'Set-WacKerberosDelegation',
        'Get-WacRbacCollectorScript', 'Get-WacRbacStatus', 'Test-WacRbac', 'Add-WacRbacMember'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
