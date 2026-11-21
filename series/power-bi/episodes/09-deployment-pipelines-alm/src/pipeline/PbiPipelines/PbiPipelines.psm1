#Requires -Version 7.2
<#
.SYNOPSIS
    Deployment pipelines through the Power BI REST API (Pipelines group + Refresh Dataset).

.DESCRIPTION
    Get-PbiPipeline / Get-PbiPipelineStage   find the pipeline by name, list its stages and workspaces
    Get-PbiStageItem                         semantic models, reports, dashboards, dataflows of a stage (Get Pipeline Stage Artifacts)
    Compare-PbiStage                         which items of the source stage are paired in the target stage, which are new, which only exist in the target
    Test-PbiDeployment                       rules before a deployment: a report without its semantic model, too many items, a target without a workspace
    New-PbiDeployRequest                     the URL and body of Deploy All or Selective Deploy
    Invoke-PbiPipelineDeploy                 runs the deployment (-WhatIf shows the request) and waits for the operation
    Wait-PbiPipelineOperation                polls Get Pipeline Operation until Succeeded or Failed
    Get-PbiDeploymentHistory                 the last deployments (up to 20)
    Start-PbiStageRefresh                    refresh of a semantic model in the target workspace: data isn't copied by a deployment

    All functions call Invoke-PowerBIRestMethod (module MicrosoftPowerBIMgmt, after Connect-PowerBIServiceAccount). Output uses
    names, never e-mail addresses. Stages are addressed by their order: Development 0, Test 1, Production 2.
#>

Set-StrictMode -Version Latest

$script:Rules = [ordered]@{
    PD001 = 'a report is selected without its semantic model, and the target stage has no paired copy of the model: the deployment fails'
    PD002 = 'more than 300 items in one deployment (the documented maximum)'
    PD003 = 'the target stage has no workspace yet: deploy with -NewWorkspaceName (the service creates it) or assign one'
    PD004 = 'an item with the same name and type exists in the target stage but is not paired: the first deployment of a new item fails'
    PD005 = 'nothing to deploy: the selected items are not in the source stage'
}

function Get-PbiPipelineRule { $script:Rules }

function New-Finding([string] $Rule, [string] $Severity, [string] $Message) {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Message = $Message }
}

function Invoke-PbiApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Get', 'Post')][string] $Method,
        [Parameter(Mandatory)][string] $Url,
        [hashtable] $Body
    )
    $params = @{ Method = $Method; Url = $Url }
    if ($Body) { $params.Body = $Body | ConvertTo-Json -Depth 6 -Compress }
    $json = Invoke-PowerBIRestMethod @params
    if ([string]::IsNullOrWhiteSpace($json)) { return $null }
    $json | ConvertFrom-Json
}

function Get-Prop($Object, [string[]] $Name) {
    foreach ($n in $Name) { if ($Object.PSObject.Properties[$n]) { return $Object.$n } }
    $null
}

function Get-PbiPipeline {
    <#
    .SYNOPSIS  Finds a pipeline by display name (Get Pipelines). Returns Id and DisplayName.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Name)
    $r = Invoke-PbiApi -Method Get -Url 'pipelines'
    $hit = @($r.value | Where-Object { $_.displayName -eq $Name })
    if ($hit.Count -ne 1) { throw "Expected one pipeline named '$Name', found $($hit.Count)." }
    [pscustomobject]@{ Id = $hit[0].id; DisplayName = $hit[0].displayName }
}

function Get-PbiPipelineStage {
    <#
    .SYNOPSIS  Stages of a pipeline with the assigned workspace (Get Pipeline Stages). A stage without a workspace has no WorkspaceId.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $PipelineId)
    $r = Invoke-PbiApi -Method Get -Url "pipelines/$PipelineId/stages"
    foreach ($s in $r.value) {
        [pscustomobject]@{
            Order         = [int] $s.order
            WorkspaceId   = Get-Prop $s @('workspaceId')
            WorkspaceName = Get-Prop $s @('workspaceName')
        }
    }
}

function Get-PbiStageItem {
    <#
    .SYNOPSIS
        Items of one stage (Get Pipeline Stage Artifacts), flattened. SourceId is the item of the stage before this one that
        updates it on the next deployment; TargetId the item of the stage after it. The two name properties differ by type in
        Learn's sample (artifactName / artifactDisplayName): both are read.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $PipelineId, [Parameter(Mandatory)][int] $StageOrder)
    $r = Invoke-PbiApi -Method Get -Url "pipelines/$PipelineId/stages/$StageOrder/artifacts"
    $map = [ordered]@{ datasets = 'SemanticModel'; reports = 'Report'; dashboards = 'Dashboard'; dataflows = 'Dataflow'; datamarts = 'Datamart' }
    foreach ($kind in $map.Keys) {
        if (-not $r.PSObject.Properties[$kind]) { continue }
        foreach ($i in $r.$kind) {
            [pscustomobject]@{
                Type           = $map[$kind]
                Name           = Get-Prop $i @('artifactDisplayName', 'artifactName')
                Id             = $i.artifactId
                SourceId       = Get-Prop $i @('sourceArtifactId')
                TargetId       = Get-Prop $i @('targetArtifactId')
                LastDeployment = Get-Prop $i @('lastDeploymentTime')
            }
        }
    }
}

function Compare-PbiStage {
    <#
    .SYNOPSIS
        Pairing between two neighbouring stages. The pairing is the one the service keeps: the item in the target stage that
        lists the source item as its SourceId. Same name and type without that link is NOT paired (a duplicate is created or,
        for a first deployment, it fails). Status: Paired | OnlyInSource (new on deploy) | OnlyInTarget (untouched by deploy).
        This is pairing and deployment time, not a content diff: the service's Compare view shows the content differences.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $PipelineId, [Parameter(Mandatory)][int] $SourceStage, [Parameter(Mandatory)][int] $TargetStage)
    $src = @(Get-PbiStageItem -PipelineId $PipelineId -StageOrder $SourceStage)
    $tgt = @(Get-PbiStageItem -PipelineId $PipelineId -StageOrder $TargetStage)
    $pairedSource = @{}
    foreach ($t in $tgt) {
        $s = if ($t.SourceId) { $src | Where-Object { $_.Id -eq $t.SourceId } | Select-Object -First 1 } else { $null }
        if ($s) {
            $pairedSource[$s.Id] = $true
            [pscustomobject]@{ Type = $t.Type; Source = $s.Name; Target = $t.Name; Status = 'Paired'; SourceId = $s.Id; TargetId = $t.Id; Renamed = ($s.Name -ne $t.Name); LastDeployment = $t.LastDeployment }
        } else {
            [pscustomobject]@{ Type = $t.Type; Source = $null; Target = $t.Name; Status = 'OnlyInTarget'; SourceId = $null; TargetId = $t.Id; Renamed = $false; LastDeployment = $t.LastDeployment }
        }
    }
    foreach ($s in $src | Where-Object { -not $pairedSource.ContainsKey($_.Id) }) {
        [pscustomobject]@{ Type = $s.Type; Source = $s.Name; Target = $null; Status = 'OnlyInSource'; SourceId = $s.Id; TargetId = $null; Renamed = $false; LastDeployment = $null }
    }
}

function Test-PbiDeployment {
    <#
    .SYNOPSIS
        Rules before a selective deployment (PD001-PD005), from the stage listings and the report -> model links of the source
        workspace. Returns findings; an error means the service would refuse or fail the deployment.
    .PARAMETER ReportModel
        Hashtable report id -> semantic model id of the source workspace (Get Reports In Group: id, datasetId).
    .PARAMETER ItemId
        Source item ids to deploy. Empty = everything in the source stage (Deploy All).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $PipelineId, [Parameter(Mandatory)][int] $SourceStage, [Parameter(Mandatory)][int] $TargetStage,
        [string[]] $ItemId = @(), [hashtable] $ReportModel = @{}
    )
    $out = [System.Collections.Generic.List[object]]::new()
    $stages = @(Get-PbiPipelineStage -PipelineId $PipelineId)
    $target = $stages | Where-Object { $_.Order -eq $TargetStage }
    if (-not $target -or -not $target.WorkspaceId) {
        $out.Add((New-Finding PD003 Info "stage $TargetStage has no workspace yet: the deployment must create one (new workspace name) or you assign one first"))
    }
    $pairs = @(Compare-PbiStage -PipelineId $PipelineId -SourceStage $SourceStage -TargetStage $TargetStage)
    $selected = @(if ($ItemId.Count) { $pairs | Where-Object { $_.SourceId -and $ItemId -contains $_.SourceId } } else { $pairs | Where-Object { $_.SourceId } })
    if ($ItemId.Count -and $selected.Count -eq 0) { $out.Add((New-Finding PD005 Error 'none of the selected ids is an item of the source stage')); return $out }
    if ($selected.Count -gt 300) { $out.Add((New-Finding PD002 Error "$($selected.Count) items selected: the maximum is 300 per deployment")) }
    foreach ($r in $selected | Where-Object { $_.Type -eq 'Report' }) {
        $model = $ReportModel[$r.SourceId]
        if (-not $model) { continue }
        $inSelection = $selected | Where-Object { $_.SourceId -eq $model }
        $pairedInTarget = $pairs | Where-Object { $_.SourceId -eq $model -and $_.Status -eq 'Paired' }
        if (-not $inSelection -and -not $pairedInTarget) {
            $m = $pairs | Where-Object { $_.SourceId -eq $model } | Select-Object -First 1
            $mname = if ($m) { $m.Source } else { 'its semantic model' }
            $out.Add((New-Finding PD001 Error "report '$($r.Source)' needs '$mname', which isn't selected and isn't in the target stage"))
        }
    }
    foreach ($n in $selected | Where-Object { $_.Status -eq 'OnlyInSource' }) {
        $clash = $pairs | Where-Object { $_.Status -eq 'OnlyInTarget' -and $_.Type -eq $n.Type -and $_.Target -eq $n.Source }
        if ($clash) { $out.Add((New-Finding PD004 Error "$($n.Type) '$($n.Source)': the target stage already has an unpaired $($n.Type) with this name, so the first deployment fails")) }
    }
    $out
}

function New-PbiDeployRequest {
    <#
    .SYNOPSIS
        URL and JSON body of Deploy All (no ids) or Selective Deploy (ids). Options follow Learn's PowerShell sample:
        allowCreateArtifact and allowOverwriteArtifact. Stage orders: Development 0, Test 1, Production 2.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $PipelineId, [Parameter(Mandatory)][ValidateRange(0, 9)][int] $SourceStage,
        [string[]] $SemanticModelId = @(), [string[]] $ReportId = @(), [string[]] $DashboardId = @(),
        [string] $Note, [switch] $Backward, [switch] $NoOverwrite, [switch] $NoCreate, [string] $NewWorkspaceName
    )
    if ($Note -and $Note.Length -gt 1024) { throw 'Note is longer than 1024 characters (the limit Learn documents for the Fabric deploy API; applied here as well).' }
    $selective = ($SemanticModelId.Count + $ReportId.Count + $DashboardId.Count) -gt 0
    $body = [ordered]@{ sourceStageOrder = $SourceStage }
    if ($selective) {
        if ($SemanticModelId.Count) { $body.datasets = @($SemanticModelId | ForEach-Object { @{ sourceId = $_ } }) }
        if ($ReportId.Count) { $body.reports = @($ReportId | ForEach-Object { @{ sourceId = $_ } }) }
        if ($DashboardId.Count) { $body.dashboards = @($DashboardId | ForEach-Object { @{ sourceId = $_ } }) }
    }
    $body.options = [ordered]@{ allowCreateArtifact = (-not $NoCreate.IsPresent); allowOverwriteArtifact = (-not $NoOverwrite.IsPresent) }
    if ($Backward) { $body.isBackwardDeployment = $true }
    if ($NewWorkspaceName) { $body.newWorkspace = @{ name = $NewWorkspaceName } }
    if ($Note) { $body.note = $Note }
    [pscustomobject]@{
        Kind = if ($selective) { 'SelectiveDeploy' } else { 'DeployAll' }
        Url  = "pipelines/$PipelineId/" + $(if ($selective) { 'Deploy' } else { 'deployAll' })
        Body = $body
    }
}

function Wait-PbiPipelineOperation {
    <#
    .SYNOPSIS
        Polls Get Pipeline Operation. The Power BI API reports NotStarted, Executing, Succeeded, Failed (the Fabric API says
        Running instead of Executing: both are treated as in progress). Throws when the operation fails, naming the failed
        steps, or when TimeoutSeconds runs out.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $PipelineId, [Parameter(Mandatory)][string] $OperationId,
        [int] $PollSeconds = 5, [int] $TimeoutSeconds = 1800)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ($true) {
        $op = Invoke-PbiApi -Method Get -Url "pipelines/$PipelineId/operations/$OperationId"
        if ($op.status -in 'Succeeded', 'Failed') { break }
        if ($op.status -notin 'NotStarted', 'Executing', 'Running') { throw "Unknown operation status '$($op.status)'." }
        if ((Get-Date) -gt $deadline) { throw "Deployment $OperationId still '$($op.status)' after $TimeoutSeconds seconds." }
        if ($PollSeconds -gt 0) { Start-Sleep -Seconds $PollSeconds }
    }
    if ($op.status -eq 'Failed') {
        $steps = @($op.executionPlan.Steps ?? $op.executionPlan.steps) | Where-Object { $_ -and $_.status -eq 'Failed' }
        $why = ($steps | ForEach-Object { "$($_.sourceAndTarget.sourceDisplayName): $($_.error.errorCode) $($_.error.errorDetails)" }) -join '; '
        throw "Deployment $OperationId failed. $why"
    }
    $op
}

function Invoke-PbiPipelineDeploy {
    <#
    .SYNOPSIS  Deploys, then waits. Supports -WhatIf (prints the request and sends nothing).
    .OUTPUTS   The finished operation: source and target stage, executionPlan with one step per item (New / Different / NoDifference).
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory)][string] $PipelineId, [Parameter(Mandatory)][ValidateRange(0, 9)][int] $SourceStage,
        [string[]] $SemanticModelId = @(), [string[]] $ReportId = @(), [string[]] $DashboardId = @(),
        [string] $Note, [switch] $Backward, [switch] $NoOverwrite, [string] $NewWorkspaceName,
        [int] $PollSeconds = 5, [int] $TimeoutSeconds = 1800
    )
    $reqParams = @{} + $PSBoundParameters
    foreach ($k in 'PollSeconds', 'TimeoutSeconds', 'WhatIf', 'Confirm', 'Verbose') { $reqParams.Remove($k) }
    $req = New-PbiDeployRequest @reqParams
    $verb = "$($req.Kind) stage $SourceStage -> $(if ($Backward) { $SourceStage - 1 } else { $SourceStage + 1 })"
    if (-not $PSCmdlet.ShouldProcess("pipeline $PipelineId", $verb)) {
        Write-Verbose ("POST {0} {1}" -f $req.Url, ($req.Body | ConvertTo-Json -Depth 6 -Compress))
        return $req
    }
    $r = Invoke-PbiApi -Method Post -Url $req.Url -Body $req.Body
    $id = if ($r.PSObject.Properties['value']) { @($r.value)[0].id } else { $r.id }
    if (-not $id) { throw 'The deploy call returned no operation id.' }
    Wait-PbiPipelineOperation -PipelineId $PipelineId -OperationId $id -PollSeconds $PollSeconds -TimeoutSeconds $TimeoutSeconds
}

function Get-PbiDeploymentHistory {
    <#
    .SYNOPSIS  Up to the 20 most recent deployments (Get Pipeline Operations): when, which stages, status, counts, who (UPN as returned).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $PipelineId)
    $r = Invoke-PbiApi -Method Get -Url "pipelines/$PipelineId/operations"
    foreach ($o in $r.value) {
        $d = Get-Prop $o @('preDeploymentDiffInformation')
        [pscustomobject]@{
            Id = $o.id; Status = $o.status; From = [int] $o.sourceStageOrder; To = [int] $o.targetStageOrder
            Start = Get-Prop $o @('executionStartTime'); End = Get-Prop $o @('executionEndTime')
            New = if ($d) { $d.newArtifactsCount } else { $null }; Different = if ($d) { $d.differentArtifactsCount } else { $null }
            Same = if ($d) { $d.noDifferenceArtifactsCount } else { $null }; Note = if (Get-Prop $o @('note')) { $o.note.content } else { $null }
        }
    }
}

function Start-PbiStageRefresh {
    <#
    .SYNOPSIS
        Refresh Dataset In Group for the semantic model in a stage's workspace. A deployment copies metadata, not data, so the
        new stage is empty until this runs (the model needs its credentials set once in the service). Standard refresh: returns
        when the request is accepted; progress is in the refresh history.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string] $WorkspaceId, [Parameter(Mandatory)][string] $SemanticModelId)
    if ($PSCmdlet.ShouldProcess("semantic model $SemanticModelId", 'refresh')) {
        Invoke-PbiApi -Method Post -Url "groups/$WorkspaceId/datasets/$SemanticModelId/refreshes" -Body @{ notifyOption = 'NoNotification' } | Out-Null
    }
}

Export-ModuleMember -Function Get-PbiPipelineRule, Get-PbiPipeline, Get-PbiPipelineStage, Get-PbiStageItem, Compare-PbiStage,
    Test-PbiDeployment, New-PbiDeployRequest, Wait-PbiPipelineOperation, Invoke-PbiPipelineDeploy, Get-PbiDeploymentHistory, Start-PbiStageRefresh
