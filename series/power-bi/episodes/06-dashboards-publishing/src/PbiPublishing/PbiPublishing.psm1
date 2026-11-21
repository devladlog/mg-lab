#Requires -Version 7.2
<#
.SYNOPSIS
    Publishing checks and dashboard automation for Power BI.

.DESCRIPTION
    Test-PbipPublishReadiness    offline: what a Power BI project (PBIP) will need after it's published
    Get-PbiWorkspaceInventory    reports, semantic models, dashboards and their tiles in one workspace (REST, read only)
    Test-PbiWorkspacePublishing  rules on that inventory: broken tiles, untitled tiles, refresh, RLS, dashboard size
    Copy-PbiDashboard            copy a dashboard tile by tile (Add Dashboard + Clone Tile): dashboards have no file
                                 format you can keep in git, the API is the only way to copy one

    The REST functions call Invoke-PowerBIRestMethod (module MicrosoftPowerBIMgmt) and need Connect-PowerBIServiceAccount
    first. Output never contains IDs or e-mail addresses: names only, so it can be recorded.
#>

Set-StrictMode -Version Latest

$script:Rules = [ordered]@{
    PUB001 = 'a local file source needs an on-premises data gateway to refresh in the service'
    PUB002 = 'parameters that point to a local path are listed'
    PUB003 = 'RLS roles: add members in the service, consumers must be Viewers or app users'
    PUB004 = 'the report points to a semantic model folder that exists'
    WS001  = 'every report tile points to a report in the workspace'
    WS002  = 'every tile has a title the API can read'
    WS003  = 'semantic models that need a gateway are flagged'
    WS004  = 'semantic models with RLS are flagged (no Publish to web)'
    WS005  = 'a dashboard holds the highlights only (tile limit)'
    WS006  = 'semantic models without refresh are flagged (tiles and alerts only change on refresh)'
}

function Get-PbiPublishingRule { $script:Rules }

function New-Finding([string] $Rule, [string] $Severity, [string] $Message) {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Message = $Message }
}

# ---------------------------------------------------------------------------------------------------------------
# Offline: the PBIP folder
# ---------------------------------------------------------------------------------------------------------------
function Test-PbipPublishReadiness {
    <#
    .SYNOPSIS
        Reads a PBIP folder (the one with the .pbip file) and reports what publishing will need.
    .EXAMPLE
        Test-PbipPublishReadiness -Path ../05-row-level-security/src
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Path)

    $pbip = Get-ChildItem -LiteralPath $Path -Filter *.pbip -File | Select-Object -First 1
    if (-not $pbip) { throw "no .pbip file in $Path" }
    $project = Get-Content -LiteralPath $pbip.FullName -Raw | ConvertFrom-Json

    foreach ($artifact in $project.artifacts) {
        $reportDir = Join-Path $Path $artifact.report.path
        $pbir = Get-Content -LiteralPath (Join-Path $reportDir 'definition.pbir') -Raw | ConvertFrom-Json
        $ref = $pbir.datasetReference
        if ($ref.PSObject.Properties.Name -contains 'byConnection' -and $ref.byConnection) {
            continue    # live connection to a published semantic model: nothing to publish with it
        }
        $modelDir = Join-Path $reportDir $ref.byPath.path
        $definition = Join-Path $modelDir 'definition'
        if (-not (Test-Path -LiteralPath (Join-Path $definition 'model.tmdl'))) {
            New-Finding PUB004 Error "report $($artifact.report.path) points to $($ref.byPath.path), which has no definition/model.tmdl"
            continue
        }

        $local = [ordered]@{}
        foreach ($f in Get-ChildItem -LiteralPath (Join-Path $definition 'tables') -Filter *.tmdl -File -ErrorAction SilentlyContinue) {
            $text = Get-Content -LiteralPath $f.FullName -Raw
            $table = [regex]::Match($text, "(?m)^table\s+('(?:[^']|'')+'|\S+)").Groups[1].Value.Trim("'")
            foreach ($m in [regex]::Matches($text, '\b(File\.Contents|Folder\.Files|Folder\.Contents)\s*\(')) {
                $local[$table] = @(@($local[$table]) + $m.Groups[1].Value | Where-Object { $_ } | Sort-Object -Unique)
            }
        }
        if ($local.Count) {
            $fns = $local.Values | ForEach-Object { $_ } | Sort-Object -Unique
            New-Finding PUB001 Warning (("{0} table(s) read local files with {1} ({2}): Desktop uploads the data when you " +
                "publish, but refresh in the service needs an on-premises data gateway") -f $local.Count, ($fns -join ', '), ($local.Keys -join ', '))
        }

        $expressions = Join-Path $definition 'expressions.tmdl'
        if (Test-Path -LiteralPath $expressions) {
            $text = Get-Content -LiteralPath $expressions -Raw
            foreach ($m in [regex]::Matches($text, '(?m)^expression\s+(\S+)\s*=\s*"((?:[^"]|"")*)"\s*meta\s*\[[^\]]*IsParameterQuery=true')) {
                $value = $m.Groups[2].Value
                if ($value -match '^[A-Za-z]:\\' -or $value -match '^\\\\') {
                    New-Finding PUB002 Info "parameter $($m.Groups[1].Value) is a local path ($value): the gateway machine needs the same path"
                }
            }
        }

        $roles = @(Get-ChildItem -LiteralPath (Join-Path $definition 'roles') -Filter *.tmdl -File -ErrorAction SilentlyContinue)
        if ($roles.Count) {
            $names = $roles | ForEach-Object { [regex]::Match((Get-Content -LiteralPath $_.FullName -Raw), "(?m)^role\s+('(?:[^']|'')+'|\S+)").Groups[1].Value.Trim("'") }
            New-Finding PUB003 Warning (("RLS roles {0}: add members on the semantic model's Security page; RLS only applies to " +
                "Viewers and app users, and Publish to web isn't available") -f ($names -join ', '))
        }
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Service: inventory and rules
# ---------------------------------------------------------------------------------------------------------------
function Invoke-PbiApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Get', 'Post')][string] $Method,
        [Parameter(Mandatory)][string] $Url,
        [hashtable] $Body
    )
    $params = @{ Method = $Method; Url = $Url }
    if ($Body) { $params.Body = $Body | ConvertTo-Json -Depth 5 -Compress }
    $json = Invoke-PowerBIRestMethod @params
    if ([string]::IsNullOrWhiteSpace($json)) { return $null }
    $json | ConvertFrom-Json
}

function Get-PbiWorkspaceInventory {
    <#
    .SYNOPSIS
        Reports, semantic models, dashboards and tiles of one workspace (Get Reports / Datasets / Dashboards / Tiles In Group).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $WorkspaceId)
    $base = "groups/$WorkspaceId"
    $dashboards = foreach ($d in @((Invoke-PbiApi Get "$base/dashboards").value)) {
        [pscustomobject]@{
            Id    = $d.id
            Name  = $d.displayName
            Tiles = @((Invoke-PbiApi Get "$base/dashboards/$($d.id)/tiles").value)
        }
    }
    [pscustomobject]@{
        WorkspaceId = $WorkspaceId
        Reports     = @((Invoke-PbiApi Get "$base/reports").value)
        Datasets    = @((Invoke-PbiApi Get "$base/datasets").value)
        Dashboards  = @($dashboards)
    }
}

function Get-Prop($Object, [string] $Name) {
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name) { $Object.$Name } else { $null }
}

function Test-PbiWorkspacePublishing {
    <#
    .SYNOPSIS
        Rules WS001-WS006 on an inventory from Get-PbiWorkspaceInventory.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, ValueFromPipeline)] $Inventory,
        [int] $MaxTiles = 12
    )
    process {
        $reportIds = @($Inventory.Reports | ForEach-Object id)
        foreach ($d in $Inventory.Dashboards) {
            $tiles = @($d.Tiles)
            if ($tiles.Count -gt $MaxTiles) {
                New-Finding WS005 Warning "dashboard '$($d.Name)' has $($tiles.Count) tiles (team limit $MaxTiles): keep the highlights, link to the report"
            }
            $i = 0
            foreach ($t in $tiles) {
                $i++
                $title = Get-Prop $t 'title'
                $label = if ($title) { "'$title'" } else { "#$i" }
                $reportId = Get-Prop $t 'reportId'
                if ($reportId -and $reportIds -notcontains $reportId) {
                    New-Finding WS001 Error "dashboard '$($d.Name)', tile $($label): its report isn't in this workspace (deleted, or cloned without a target report)"
                }
                if (-not $title) {
                    New-Finding WS002 Warning (("dashboard '{0}', tile #{1} has no title in the API: titles set in the report before pinning " +
                        "aren't returned, set them in the dashboard (Edit details)") -f $d.Name, $i)
                }
            }
        }
        foreach ($ds in $Inventory.Datasets) {
            if (Get-Prop $ds 'isOnPremGatewayRequired') {
                New-Finding WS003 Warning "semantic model '$($ds.name)' needs an on-premises data gateway to refresh"
            }
            if (Get-Prop $ds 'isEffectiveIdentityRolesRequired') {
                New-Finding WS004 Info "semantic model '$($ds.name)' has RLS: share it with Viewers or through an app; Publish to web isn't available"
            }
            if ((Get-Prop $ds 'isRefreshable') -eq $false) {
                New-Finding WS006 Warning "semantic model '$($ds.name)' isn't refreshed or scheduled: tiles and data alerts won't change"
            }
        }
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Service: copy a dashboard
# ---------------------------------------------------------------------------------------------------------------
function Copy-PbiDashboard {
    <#
    .SYNOPSIS
        Creates a new dashboard and clones every tile of the source into it (Add Dashboard In Group + Clone Tile In Group).
    .DESCRIPTION
        Same workspace: tiles keep their report and semantic model links. Another workspace: pass the report and semantic
        model the tiles must be bound to there; Learn: without them, tiles cloned to another workspace are broken.
    .EXAMPLE
        Copy-PbiDashboard -WorkspaceId $ws -DashboardId $daily -NewName 'Contoso Bikes - Store managers' -WhatIf
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $DashboardId,
        [Parameter(Mandatory)][string] $NewName,
        [string] $TargetWorkspaceId,
        [string] $TargetReportId,
        [string] $TargetDatasetId
    )
    $crossWorkspace = $TargetWorkspaceId -and $TargetWorkspaceId -ne $WorkspaceId
    $tiles = @((Invoke-PbiApi Get "groups/$WorkspaceId/dashboards/$DashboardId/tiles").value)
    if ($crossWorkspace) {
        if (-not $TargetReportId -or -not $TargetDatasetId) {
            throw 'cloning to another workspace needs -TargetReportId and -TargetDatasetId, or the tiles are broken'
        }
        $sources = @($tiles | ForEach-Object { Get-Prop $_ 'reportId' } | Where-Object { $_ } | Sort-Object -Unique)
        if ($sources.Count -gt 1) {
            throw "the dashboard has tiles from $($sources.Count) reports; one target report can't rebind them all"
        }
    }
    $targetWs = if ($crossWorkspace) { $TargetWorkspaceId } else { $WorkspaceId }
    if (-not $PSCmdlet.ShouldProcess("$NewName ($($tiles.Count) tiles)", 'Create dashboard and clone tiles')) { return }

    $new = Invoke-PbiApi Post "groups/$targetWs/dashboards" @{ name = $NewName }
    $cloned = 0
    foreach ($t in $tiles) {
        $body = @{ targetDashboardId = $new.id; positionConflictAction = 'Tail' }
        if ($crossWorkspace) {
            $body.targetWorkspaceId = $TargetWorkspaceId
            if (Get-Prop $t 'reportId') { $body.targetReportId = $TargetReportId }
            if (Get-Prop $t 'datasetId') { $body.targetModelId = $TargetDatasetId }
        }
        $null = Invoke-PbiApi Post "groups/$WorkspaceId/dashboards/$DashboardId/tiles/$($t.id)/Clone" $body
        $cloned++
    }
    [pscustomobject]@{ Dashboard = $new.displayName; Tiles = $cloned; SameWorkspace = -not $crossWorkspace }
}

Export-ModuleMember -Function Get-PbiPublishingRule, Test-PbipPublishReadiness, Get-PbiWorkspaceInventory,
    Test-PbiWorkspacePublishing, Copy-PbiDashboard
