@{
    RootModule        = 'GatewayOps.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-00000000000e'
    Author            = 'MG Lab'
    Description       = 'On-premises data gateway operations (DEVLADLOG Power BI #14): network check, data source match check, data source creation with encrypted credentials, binding, refresh.'
    PowerShellVersion = '7.2'
    FunctionsToExport = @('Get-GatewayEndpoint', 'Test-GatewayNetwork', 'Get-GatewayCluster', 'Get-GatewayDataSource',
        'Get-MSqlSource', 'Test-DataSourceMatch', 'New-GatewayDataSourceRequest', 'New-GatewayDataSource',
        'Get-DatasetGatewayInfo', 'Set-DatasetGateway', 'Start-DatasetRefreshAndWait', 'Get-RefreshErrorCode',
        'Set-GatewaySqlTrustedServer')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ ExternalModuleDependencies = @('MicrosoftPowerBIMgmt') } }
}
