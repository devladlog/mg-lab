#Requires -Version 7.2
<#
.SYNOPSIS
    Promotes the semantic model and report from one pipeline stage to the next: compare, check, deploy, then refresh.

.DESCRIPTION
    1. finds the pipeline by name and prints which items are paired in the target stage
    2. runs the pre-deployment rules (a report without its model, unpaired name clashes, the 300 item limit)
    3. deploys (Selective Deploy of the semantic model + report named below; Deploy All with -All), waits for the operation
    4. starts a refresh of the model in the target workspace (a deployment copies metadata, not data)

    -WhatIf prints every request and sends nothing. Needs Connect-PowerBIServiceAccount first (a user who is a pipeline admin
    and at least a contributor in both workspaces). Exit code 1 when a rule fails or the deployment fails.

.EXAMPLE
    ./Invoke-PipelineRelease.ps1 -PipelineName 'Contoso Sales (Lab)' -From 0 -Note 'Release 1' -WhatIf
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)][string] $PipelineName,
    [Parameter(Mandatory)][ValidateRange(0, 8)][int] $From,
    [string] $ModelName = 'ContosoSales',
    [string] $ReportName = 'ContosoSales',
    [switch] $All,
    [string] $Note,
    [string] $NewWorkspaceName,
    [switch] $SkipRefresh
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PbiPipelines' 'PbiPipelines.psd1')
$to = $From + 1

$pipe = Get-PbiPipeline -Name $PipelineName
$stages = @(Get-PbiPipelineStage -PipelineId $pipe.Id)
$src = $stages | Where-Object Order -eq $From
$tgt = $stages | Where-Object Order -eq $to
if (-not $src -or -not $src.WorkspaceId) { throw "Stage $From has no workspace: nothing to deploy." }

Write-Host "Pipeline '$($pipe.DisplayName)': stage $From ($($src.WorkspaceName)) -> stage $to ($(if ($tgt.WorkspaceName) { $tgt.WorkspaceName } else { 'no workspace yet' }))"
$pairs = @(Compare-PbiStage -PipelineId $pipe.Id -SourceStage $From -TargetStage $to)
$pairs | Sort-Object Type, Source | Format-Table Type, Source, Target, Status, LastDeployment -AutoSize | Out-String | Write-Host

$model = $pairs | Where-Object { $_.Type -eq 'SemanticModel' -and $_.Source -eq $ModelName } | Select-Object -First 1
$report = $pairs | Where-Object { $_.Type -eq 'Report' -and $_.Source -eq $ReportName } | Select-Object -First 1
$ids = @()
$reportModel = @{}
if (-not $All) {
    if (-not $model) { throw "Semantic model '$ModelName' is not in stage $From." }
    $ids += $model.SourceId
    if ($report) {
        $ids += $report.SourceId
        $links = (Invoke-PowerBIRestMethod -Method Get -Url "groups/$($src.WorkspaceId)/reports" | ConvertFrom-Json).value
        foreach ($l in $links) { $reportModel[$l.id] = $l.datasetId }
    }
}
$findings = @(Test-PbiDeployment -PipelineId $pipe.Id -SourceStage $From -TargetStage $to -ItemId $ids -ReportModel $reportModel)
$findings | ForEach-Object { Write-Host ("  {0,-7} {1}  {2}" -f $_.Severity.ToUpper(), $_.Rule, $_.Message) }
if ($findings | Where-Object Severity -eq 'Error') { Write-Host 'Fix the errors above first.'; exit 1 }

$deploy = @{ PipelineId = $pipe.Id; SourceStage = $From }
if (-not $All) {
    $deploy.SemanticModelId = @($model.SourceId)
    if ($report) { $deploy.ReportId = @($report.SourceId) }
}
if ($Note) { $deploy.Note = $Note }
if ($NewWorkspaceName) { $deploy.NewWorkspaceName = $NewWorkspaceName }
$op = Invoke-PbiPipelineDeploy @deploy -WhatIf:$WhatIfPreference -Confirm:$false
if ($WhatIfPreference) { Write-Host ("WhatIf: {0} {1}" -f $op.Url, ($op.Body | ConvertTo-Json -Depth 6 -Compress)); return }
Write-Host "Deployment $($op.id): $($op.status)"
$op.executionPlan.Steps | ForEach-Object { Write-Host ("  {0,-20} {1,-13} {2}" -f $_.type, $_.preDeploymentDiffState, $_.sourceAndTarget.sourceDisplayName) }

if (-not $SkipRefresh) {
    $stagesAfter = @(Get-PbiPipelineStage -PipelineId $pipe.Id)
    $targetWs = ($stagesAfter | Where-Object Order -eq $to).WorkspaceId
    $targetModel = (Get-PbiStageItem -PipelineId $pipe.Id -StageOrder $to | Where-Object { $_.Type -eq 'SemanticModel' -and $_.SourceId -eq $model.SourceId }).Id
    if ($targetWs -and $targetModel) {
        Write-Host 'Starting the refresh of the model in the target stage (data is not copied by a deployment).'
        Start-PbiStageRefresh -WorkspaceId $targetWs -SemanticModelId $targetModel
    }
}
