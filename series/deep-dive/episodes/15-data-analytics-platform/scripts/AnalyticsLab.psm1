# Helpers for the episode 15 demo. They never sign in: run `az login` yourself first; sqlcmd uses your Entra identity (-G).
Set-StrictMode -Version Latest

function Get-AnalyticsSqlPlan {
    <#
    .SYNOPSIS  The ordered list of SQL scripts for one target, with the database each one runs in and its sqlcmd variables.
    .PARAMETER Target  Source (Azure SQL source database) or Synapse (serverless endpoint).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Source', 'Synapse')][string]$Target,
        [string]$Root = (Join-Path $PSScriptRoot '..' 'sql'),
        [string]$StorageAccount,
        [string]$FactoryName,
        [string]$SourceDatabase = 'sourcedb',
        [string]$AnalyticsDatabase = 'contoso_analytics',
        [switch]$IncludeRiskScore
    )
    if ($Target -eq 'Source') {
        if (-not $FactoryName) { throw 'FactoryName is required for the Source target (the factory identity gets its database user).' }
        return @([pscustomobject]@{ File = Join-Path $Root 'source' '001-source-schema.sql'; Database = $SourceDatabase; Variables = @{ AdfName = $FactoryName } })
    }
    if (-not $StorageAccount) { throw 'StorageAccount is required for the Synapse target.' }
    $steps = @(
        [pscustomobject]@{ File = '000-database.sql'; Database = 'master'; Variables = @{} }
        [pscustomobject]@{ File = '010-lake.sql'; Database = $AnalyticsDatabase; Variables = @{ StorageAccount = $StorageAccount } }
        [pscustomobject]@{ File = '020-bronze.sql'; Database = $AnalyticsDatabase; Variables = @{} }
        [pscustomobject]@{ File = '030-silver.sql'; Database = $AnalyticsDatabase; Variables = @{} }
        [pscustomobject]@{ File = '040-gold.sql'; Database = $AnalyticsDatabase; Variables = @{} }
    )
    if ($IncludeRiskScore) { $steps += [pscustomobject]@{ File = '050-risk-score.sql'; Database = $AnalyticsDatabase; Variables = @{} } }
    $steps += [pscustomobject]@{ File = '060-quality.sql'; Database = $AnalyticsDatabase; Variables = @{} }
    foreach ($s in $steps) { $s.File = Join-Path $Root 'synapse' $s.File }
    $steps
}

function Get-SqlcmdArguments {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Server,
        [Parameter(Mandatory)]$Step
    )
    $args = @('-S', $Server, '-d', $Step.Database, '-G', '-b', '-i', $Step.File)
    foreach ($k in ($Step.Variables.Keys | Sort-Object)) { $args += @('-v', "$k=$($Step.Variables[$k])") }
    , $args
}

function Invoke-AnalyticsSql {
    <#
    .SYNOPSIS  Runs a plan with sqlcmd, stopping at the first failing script. Supports -WhatIf.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$Server,
        [Parameter(Mandatory)][object[]]$Plan
    )
    foreach ($step in $Plan) {
        if (-not (Test-Path $step.File)) { throw "Script not found: $($step.File)" }
        $sqlcmdArgs = Get-SqlcmdArguments -Server $Server -Step $step
        $run = $PSCmdlet.ShouldProcess("$Server/$($step.Database)", "sqlcmd $(Split-Path $step.File -Leaf)")
        if ($run) {
            & sqlcmd @sqlcmdArgs
            if ($LASTEXITCODE -ne 0) { throw "sqlcmd failed on $(Split-Path $step.File -Leaf) (exit $LASTEXITCODE)." }
        }
        [pscustomobject]@{ Script = Split-Path $step.File -Leaf; Database = $step.Database; Executed = [bool]$run }
    }
}

function Get-LakePullCommand {
    <# .SYNOPSIS  The az command that copies the bronze files to a local folder (Entra login, no keys). #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$StorageAccount,
        [Parameter(Mandatory)][string]$Destination
    )
    "az storage blob download-batch --account-name $StorageAccount --auth-mode login --source lake --pattern 'bronze/*' --destination `"$Destination`""
}

Export-ModuleMember -Function Get-AnalyticsSqlPlan, Get-SqlcmdArguments, Invoke-AnalyticsSql, Get-LakePullCommand
