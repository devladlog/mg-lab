@{
    RootModule        = 'NetLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000000'
    Author            = 'Momento Galatico'
    Description       = 'DEVLADLOG Windows Server #4: DNS and DHCP from one definition file (idempotent), snapshot export and health report.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @(
        'ConvertTo-NetLabUInt32', 'Test-NetLabIpInRange', 'ConvertTo-NetLabReverseZoneName', 'Get-NetLabPtrName', 'Read-NetLabDefinition',
        'Test-NetLabHealth', 'ConvertTo-NetLabMarkdown', 'Invoke-NetLabDnsDeployment', 'Invoke-NetLabDhcpDeployment', 'Export-NetLabSnapshot'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
