<#
.SYNOPSIS
  Run a desktop flow from code through Dataverse (RunDesktopFlow), wait for it, return its outputs.
.DESCRIPTION
  Learn: "Work with desktop flows using code".
    POST workflows(<id>)/Microsoft.Dynamics.CRM.RunDesktopFlow   -> flowsessionId
    GET  flowsessions(<id>)?$select=statuscode,statecode,startedon,completedon   (polling; needs Owner privileges)
    GET  flowsessions(<id>)/outputs/$value                        (outputs of the run)
    POST flowsessions(<id>)/Microsoft.Dynamics.CRM.CancelDesktopFlowRun
  flowsession.statuscode (table reference): 1 Paused, 2 Running, 3 Waiting, 6 Suspended are still in progress; 4 Succeeded,
  5 Skipped, 7 Cancelled, 8 Failed, 9 Faulted, 10 TimedOut, 11 Aborted, 12 Ignored, 14 Terminated end the run.
  Token: $env:DATAVERSE_TOKEN. Throws when the run does not end Succeeded.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $OrgUrl,
    [Parameter(Mandatory)] [string] $DesktopFlowId,
    [Parameter(Mandatory)] [string] $ConnectionName,
    [ValidateSet('attended', 'unattended')] [string] $RunMode = 'attended',
    [ValidateSet('normal', 'high')] [string] $RunPriority = 'normal',
    [hashtable] $Inputs = @{},
    [int] $TimeoutSeconds = 7200,
    [int] $PollSeconds = 10,
    [int] $MaxWaitSeconds = 1800,
    [switch] $NoWait
)
$ErrorActionPreference = 'Stop'
if (-not $env:DATAVERSE_TOKEN) { throw 'Set $env:DATAVERSE_TOKEN to a bearer token for the environment first.' }
if ($DesktopFlowId -notmatch '^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$') { throw "DesktopFlowId is not a GUID: $DesktopFlowId" }
$inputsJson = ($Inputs | ConvertTo-Json -Compress -Depth 5)
if ([System.Text.Encoding]::UTF8.GetByteCount($inputsJson) -gt 2MB) { throw 'The inputs are larger than 2 MB, the limit of a desktop flow input.' }

$base = $OrgUrl.TrimEnd('/') + '/api/data/v9.2'
$headers = @{ Authorization = "Bearer $env:DATAVERSE_TOKEN"; Accept = 'application/json' }
$ended = @{ 4 = 'Succeeded'; 5 = 'Skipped'; 7 = 'Cancelled'; 8 = 'Failed'; 9 = 'Faulted'; 10 = 'TimedOut'; 11 = 'Aborted'; 12 = 'Ignored'; 14 = 'Terminated' }

function Invoke-Dv([string] $Method, [string] $Path, $Body) {
    $p = @{ Method = $Method; Uri = "$base/$Path"; Headers = $headers }
    if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Compress -Depth 5); $p.ContentType = 'application/json' }
    Invoke-RestMethod @p
}

$body = [ordered]@{
    runMode        = $RunMode
    runPriority    = $RunPriority
    connectionName = $ConnectionName
    timeout        = $TimeoutSeconds
    inputs         = $inputsJson   # a JSON string inside the JSON body, as in the Learn example
}
if (-not $PSCmdlet.ShouldProcess("workflows($DesktopFlowId)", "RunDesktopFlow ($RunMode) with $inputsJson")) { return $body }

$start = Invoke-Dv POST "workflows($DesktopFlowId)/Microsoft.Dynamics.CRM.RunDesktopFlow" $body
$sessionId = $start.flowsessionId
if ($NoWait) { return [pscustomobject]@{ flowsessionId = $sessionId; status = 'Started' } }

$waited = 0
while ($true) {
    $s = Invoke-Dv GET "flowsessions($sessionId)?`$select=statuscode,statecode,startedon,completedon" $null
    if ($ended.ContainsKey([int]$s.statuscode)) { break }
    if ($waited -ge $MaxWaitSeconds) {
        Invoke-Dv POST "flowsessions($sessionId)/Microsoft.Dynamics.CRM.CancelDesktopFlowRun" $null | Out-Null
        throw "Gave up after $MaxWaitSeconds s and cancelled flow session $sessionId."
    }
    Start-Sleep -Seconds $PollSeconds
    $waited += $PollSeconds
}
$status = $ended[[int]$s.statuscode]
$outputs = $null
if ($status -eq 'Succeeded') { $outputs = Invoke-Dv GET "flowsessions($sessionId)/outputs/`$value" $null }
$result = [pscustomobject]@{ flowsessionId = $sessionId; status = $status; startedOn = $s.startedon; completedOn = $s.completedon; outputs = $outputs }
if ($status -ne 'Succeeded') { throw "Desktop flow run $sessionId ended $status." }
$result
