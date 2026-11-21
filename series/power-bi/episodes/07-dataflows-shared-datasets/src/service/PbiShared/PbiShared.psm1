#Requires -Version 7.2
<#
.SYNOPSIS
    Audit and wiring for shared semantic models and the dataflows behind them (Power BI REST API).

.DESCRIPTION
    Get-PbiSharedModelInventory  semantic models, reports, dataflows and dataset-to-dataflow links of several workspaces
                                 (REST, read only)
    Test-PbiSharedModel          rules on that inventory: duplicate models, thin-report impact, models that still do
                                 their own data prep, reports whose model can't be found
    Set-PbiModelParameter        Update Parameters In Group: point the shared model at the dataflow of THIS workspace
                                 (WorkspaceId and DataflowId parameters), supports -WhatIf

    The functions call Invoke-PowerBIRestMethod (module MicrosoftPowerBIMgmt) and need Connect-PowerBIServiceAccount
    first. Output uses workspace NAMES you pass in, never IDs or e-mail addresses.
#>

Set-StrictMode -Version Latest

$script:Rules = [ordered]@{
    SM001 = 'a semantic model name exists in more than one workspace: which copy is the source of truth?'
    SM002 = 'a shared model is used by reports in other workspaces (thin reports): the impact of changing or deleting it'
    SM003 = 'a model in the data workspace has no upstream dataflow: its data prep is not reusable'
    SM004 = 'a report points to a semantic model that is in none of the inspected workspaces'
}

function Get-PbiSharedModelRule { $script:Rules }

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
    if ($Body) { $params.Body = $Body | ConvertTo-Json -Depth 5 -Compress }
    $json = Invoke-PowerBIRestMethod @params
    if ([string]::IsNullOrWhiteSpace($json)) { return $null }
    $json | ConvertFrom-Json
}

function Get-PbiSharedModelInventory {
    <#
    .SYNOPSIS
        Reads semantic models, reports, dataflows and dataset-to-dataflow links of the given workspaces.
    .PARAMETER Workspace
        Name -> ID of each workspace, e.g. @{ 'Contoso Data (Lab)' = $dataWs; 'Contoso Sales (Lab)' = $salesWs }.
    .EXAMPLE
        Get-PbiSharedModelInventory -Workspace @{ 'Contoso Data (Lab)' = $dataWs; 'Contoso Sales (Lab)' = $salesWs }
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][System.Collections.IDictionary] $Workspace)

    $items = foreach ($name in $Workspace.Keys) {
        $base = "groups/$($Workspace[$name])"
        [pscustomobject]@{
            Name      = $name
            Datasets  = @((Invoke-PbiApi Get "$base/datasets").value)
            Reports   = @((Invoke-PbiApi Get "$base/reports").value)
            Dataflows = @((Invoke-PbiApi Get "$base/dataflows").value)
            Links     = @((Invoke-PbiApi Get "$base/datasets/upstreamDataflows").value)
        }
    }
    [pscustomobject]@{ Workspaces = @($items) }
}

function Test-PbiSharedModel {
    <#
    .SYNOPSIS
        Applies the SM rules to an inventory from Get-PbiSharedModelInventory.
    .PARAMETER DataWorkspace
        Name of the workspace that owns the shared models and the dataflows (SM003 only looks there).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, ValueFromPipeline)] $Inventory,
        [Parameter(Mandatory)][string] $DataWorkspace
    )
    process {
        $owner = @{}          # dataset id -> @{ Workspace; Name }
        $byName = @{}         # dataset name -> workspace names
        foreach ($ws in $Inventory.Workspaces) {
            foreach ($d in $ws.Datasets) {
                $owner[$d.id] = @{ Workspace = $ws.Name; Name = $d.name }
                $byName[$d.name] = @(@($byName[$d.name]) + $ws.Name | Where-Object { $_ })
            }
        }

        foreach ($name in ($byName.Keys | Sort-Object)) {
            $where = @($byName[$name] | Sort-Object -Unique)
            if ($where.Count -gt 1) {
                New-Finding SM001 Warning ("semantic model '{0}' exists in {1}: reports bound to the copy in their own workspace don't see the other one's data, measures or roles" -f $name, ($where -join ' and '))
            }
        }

        $thin = @{}           # "model@workspace" -> thin report names
        foreach ($ws in $Inventory.Workspaces) {
            foreach ($r in $ws.Reports) {
                if (-not ($r.PSObject.Properties.Name -contains 'datasetId') -or -not $r.datasetId) { continue }   # paginated reports
                $o = $owner[$r.datasetId]
                if (-not $o) {
                    New-Finding SM004 Warning ("report '{0}' in {1} uses a semantic model that is in none of the inspected workspaces" -f $r.name, $ws.Name)
                }
                elseif ($o.Workspace -ne $ws.Name) {
                    $key = "{0}`t{1}" -f $o.Name, $o.Workspace
                    $thin[$key] = @(@($thin[$key]) + ("{0} ({1})" -f $r.name, $ws.Name) | Where-Object { $_ })
                }
            }
        }
        foreach ($key in ($thin.Keys | Sort-Object)) {
            $modelName, $ownerWs = $key -split "`t"
            New-Finding SM002 Info ("'{0}' in {1} is used by {2} report(s) in other workspaces: {3}. It can't be deleted while they exist" -f $modelName, $ownerWs, $thin[$key].Count, ($thin[$key] -join ', '))
        }

        $data = $Inventory.Workspaces | Where-Object Name -eq $DataWorkspace
        if ($data) {
            $linked = @($data.Links | ForEach-Object { $_.datasetObjectId })
            foreach ($d in $data.Datasets) {
                if ($d.id -notin $linked) {
                    New-Finding SM003 Warning ("semantic model '{0}' in {1} has no upstream dataflow: it prepares its own data" -f $d.name, $DataWorkspace)
                }
            }
        }
    }
}

function Set-PbiModelParameter {
    <#
    .SYNOPSIS
        Sets M parameters of a published semantic model (Datasets - Update Parameters In Group).
    .DESCRIPTION
        The shared model reads the dataflow through the parameters WorkspaceId and DataflowId, because both IDs differ
        in every workspace. Learn: the caller must own the semantic model; refresh it afterwards to apply the values.
    .EXAMPLE
        Set-PbiModelParameter -WorkspaceId $ws -DatasetId $model -Parameter @{ WorkspaceId = $ws; DataflowId = $df } -WhatIf
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $DatasetId,
        [Parameter(Mandatory)][System.Collections.IDictionary] $Parameter
    )
    if ($Parameter.Count -eq 0) { throw 'the parameter list can''t be empty' }
    $details = @($Parameter.Keys | Sort-Object | ForEach-Object { @{ name = $_; newValue = [string] $Parameter[$_] } })
    if (-not $PSCmdlet.ShouldProcess(("parameters {0}" -f ($Parameter.Keys -join ', ')), 'Update semantic model parameters')) { return }
    $null = Invoke-PbiApi Post "groups/$WorkspaceId/datasets/$DatasetId/Default.UpdateParameters" @{ updateDetails = $details }
    [pscustomobject]@{ Updated = @($Parameter.Keys | Sort-Object); NextStep = 'refresh the semantic model to apply the new values' }
}

Export-ModuleMember -Function Get-PbiSharedModelRule, Get-PbiSharedModelInventory, Test-PbiSharedModel, Set-PbiModelParameter
