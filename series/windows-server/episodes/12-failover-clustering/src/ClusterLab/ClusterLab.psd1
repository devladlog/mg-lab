@{
    RootModule        = 'ClusterLab.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000012'
    Author            = 'DEVLADLOG'
    Description       = 'Failover cluster readiness check, build plan, quorum maths, failover drill and outage measurement for the DEVLADLOG lab.'
    PowerShellVersion = '5.1'
    FunctionsToExport = @('Read-ClfLabConfig', 'Get-ClfCollectorScript', 'Get-ClfFacts', 'Test-ClfReadiness', 'Get-ClfQuorumMath',
        'ConvertTo-ClfMarkdown', 'Get-ClfBuildPlan', 'Get-ClfRemovePlan', 'Invoke-ClfPlan', 'Invoke-ClfDrain', 'Invoke-ClfProbe', 'Get-ClfProbeSummary')
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
