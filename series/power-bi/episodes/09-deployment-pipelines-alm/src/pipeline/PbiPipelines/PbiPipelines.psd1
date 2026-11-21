@{
    RootModule        = 'PbiPipelines.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000009'
    Author            = 'MG Lab'
    Description       = 'Deployment pipelines through the Power BI REST API: stage items, pairing, pre-deploy checks, deploy and wait (DEVLADLOG Power BI #9).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @('Get-PbiPipelineRule', 'Get-PbiPipeline', 'Get-PbiPipelineStage', 'Get-PbiStageItem', 'Compare-PbiStage',
        'Test-PbiDeployment', 'New-PbiDeployRequest', 'Wait-PbiPipelineOperation', 'Invoke-PbiPipelineDeploy',
        'Get-PbiDeploymentHistory', 'Start-PbiStageRefresh')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ ExternalModuleDependencies = @('MicrosoftPowerBIMgmt') } }
}
