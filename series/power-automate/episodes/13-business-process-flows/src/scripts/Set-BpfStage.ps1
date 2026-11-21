<#
.SYNOPSIS
  Inspect and move business process flow instances through the Dataverse Web API.
.DESCRIPTION
  Implements the calls from "Work with business process flows using code" on Microsoft Learn:
    ListStages     GET  processstages?$filter=processid/workflowid eq <definition id>
    ListInstances  GET  <bpf table>
    Next/Previous  RetrieveActivePath + PATCH <bpf table>(<id>) with activestageid and traversedpath
    Abort/Reactivate/Finish  PATCH statecode/statuscode (1/3, 0/1, 0/2)
  The access token comes from $env:DATAVERSE_TOKEN (never from a parameter or a file in the repo).
  Use -WhatIf to print the requests without sending the PATCH.
.EXAMPLE
  $env:DATAVERSE_TOKEN = '<bearer token for the environment>'
  ./Set-BpfStage.ps1 -OrgUrl https://contoso.crm4.dynamics.com -BpfTable cts_purchaserequestprocesses `
      -Operation Next -InstanceId 00000000-0000-0000-0000-0000000000b1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $OrgUrl,
    [Parameter(Mandatory)] [ValidateSet('ListStages', 'ListInstances', 'Next', 'Previous', 'Abort', 'Reactivate', 'Finish')]
    [string] $Operation,
    [string] $BpfTable,
    [string] $InstanceId,
    [string] $DefinitionId,
    [string] $ApiVersion = 'v9.2'
)

$ErrorActionPreference = 'Stop'
if (-not $env:DATAVERSE_TOKEN) { throw 'Set $env:DATAVERSE_TOKEN to a bearer token for the environment first.' }
$guid = '^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$'
foreach ($pair in @(@('InstanceId', $InstanceId), @('DefinitionId', $DefinitionId))) {
    if ($pair[1] -and $pair[1] -notmatch $guid) { throw "$($pair[0]) is not a GUID: $($pair[1])" }
}

$base = $OrgUrl.TrimEnd('/') + "/api/data/$ApiVersion"
$headers = @{
    Authorization      = "Bearer $env:DATAVERSE_TOKEN"
    Accept             = 'application/json'
    'OData-MaxVersion' = '4.0'
    'OData-Version'    = '4.0'
}

function Invoke-Dv([string] $Method, [string] $Path, $Body) {
    $args2 = @{ Method = $Method; Uri = "$base/$Path"; Headers = $headers }
    if ($null -ne $Body) {
        $args2.Body = ($Body | ConvertTo-Json -Depth 5 -Compress)
        $args2.ContentType = 'application/json; charset=utf-8'
    }
    Invoke-RestMethod @args2
}

function Get-ActivePath([string] $Id) {
    # unbound function: the Guid is not quoted in the URL
    (Invoke-Dv GET "RetrieveActivePath(ProcessInstanceId=$Id)").value
}

function Move-Stage([int] $Offset) {
    if (-not $BpfTable -or -not $InstanceId) { throw '-BpfTable and -InstanceId are required.' }
    $inst = Invoke-Dv GET "$BpfTable($InstanceId)?`$select=_activestageid_value,traversedpath,statecode"
    if ($inst.statecode -ne 0) { throw 'The process instance is not active (statecode is not 0).' }
    $active = $inst._activestageid_value
    $traversed = @(($inst.traversedpath -split ',') | Where-Object { $_ })
    if ($Offset -lt 0) {
        # one step back: the stage visited before the active one
        if ($traversed.Count -lt 2) { throw 'Already at the first stage.' }
        $target = $traversed[$traversed.Count - 2]
        $newPath = $traversed[0..($traversed.Count - 2)]
    }
    else {
        $path = @(Get-ActivePath $InstanceId)
        $i = [array]::IndexOf(@($path | ForEach-Object { $_.processstageid }), $active)
        if ($i -lt 0) { throw 'The active stage is not on the active path.' }
        if ($i -ge $path.Count - 1) { throw 'Last stage: use -Operation Finish instead of Next.' }
        $target = $path[$i + 1].processstageid
        $newPath = $traversed + $target
    }
    $body = [ordered]@{
        'activestageid@odata.bind' = "/processstages($target)"
        traversedpath              = ($newPath -join ',')
    }
    if ($PSCmdlet.ShouldProcess("$BpfTable($InstanceId)", "PATCH $($body | ConvertTo-Json -Compress)")) {
        Invoke-Dv PATCH "$BpfTable($InstanceId)" $body | Out-Null
    }
    $body
}

switch ($Operation) {
    'ListStages' {
        if (-not $DefinitionId) { throw '-DefinitionId (workflowid of the process) is required.' }
        (Invoke-Dv GET "processstages?`$select=stagename&`$filter=processid/workflowid eq $DefinitionId").value
    }
    'ListInstances' {
        if (-not $BpfTable) { throw '-BpfTable is required.' }
        (Invoke-Dv GET "$BpfTable`?`$select=_activestageid_value,statecode,statuscode,traversedpath").value
    }
    'Next' { Move-Stage 1 }
    'Previous' { Move-Stage -1 }
    default {
        if (-not $BpfTable -or -not $InstanceId) { throw '-BpfTable and -InstanceId are required.' }
        $states = @{ Abort = @(1, 3); Reactivate = @(0, 1); Finish = @(0, 2) }
        $body = [ordered]@{ statecode = $states[$Operation][0]; statuscode = $states[$Operation][1] }
        if ($PSCmdlet.ShouldProcess("$BpfTable($InstanceId)", "PATCH $($body | ConvertTo-Json -Compress)")) {
            Invoke-Dv PATCH "$BpfTable($InstanceId)" $body | Out-Null
        }
        $body
    }
}
