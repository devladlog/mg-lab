#Requires -Version 7.2
<#
.SYNOPSIS
    Enhanced refresh of a semantic model through the Power BI REST API (Refresh Dataset In Group with the enhanced parameters),
    for models with an incremental refresh policy: refresh one partition, skip the policy, pretend it is another day.

.DESCRIPTION
    New-PbiRefreshRequest     URL and JSON body; checks the combinations Learn rules out (partialBatch with the policy applied,
                              timeout x attempts over 24 hours, effectiveDate without the policy, unknown type)
    Start-PbiEnhancedRefresh  POST /refreshes (-WhatIf shows the request and sends nothing); returns the request id
    Get-PbiRefresh            GET /refreshes (history) or /refreshes/<requestId> (one operation, with per-object status)
    Wait-PbiRefresh           polls one operation until it is no longer InProgress; throws when it didn't complete
    Stop-PbiRefresh           DELETE /refreshes/<requestId> (enhanced refreshes only)

    All functions call Invoke-PowerBIRestMethod (module MicrosoftPowerBIMgmt, after Connect-PowerBIServiceAccount).
    The service accepts one refresh at a time for a model: a second request returns 400.
#>

Set-StrictMode -Version Latest

$script:Types = 'full', 'clearValues', 'calculate', 'dataOnly', 'automatic', 'defragment'   # 'add' isn't supported (Learn)

function Invoke-PbiApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Get', 'Post', 'Delete')][string] $Method,
        [Parameter(Mandatory)][string] $Url,
        [hashtable] $Body
    )
    $params = @{ Method = $Method; Url = $Url }
    if ($Body) { $params.Body = $Body | ConvertTo-Json -Depth 6 -Compress }
    $json = Invoke-PowerBIRestMethod @params
    if ([string]::IsNullOrWhiteSpace($json)) { return $null }
    $json | ConvertFrom-Json
}

function New-PbiRefreshRequest {
    <#
    .SYNOPSIS  The URL and body of an enhanced refresh. -Partition needs -Table. -SkipRefreshPolicy sends applyRefreshPolicy = false.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId, [Parameter(Mandatory)][string] $SemanticModelId,
        [ValidateSet('full', 'clearValues', 'calculate', 'dataOnly', 'automatic', 'defragment')][string] $Type = 'full',
        [ValidateSet('transactional', 'partialBatch')][string] $CommitMode = 'transactional',
        [string] $Table, [string[]] $Partition = @(),
        [switch] $SkipRefreshPolicy, [datetime] $EffectiveDate,
        [ValidateRange(1, 64)][int] $MaxParallelism, [ValidateRange(0, 10)][int] $RetryCount = 0, [timespan] $Timeout
    )
    if ($Partition.Count -and -not $Table) { throw '-Partition needs -Table (Learn: an object is a table, or a table and a partition).' }
    if ($CommitMode -eq 'partialBatch' -and -not $SkipRefreshPolicy) {
        throw 'commitMode partialBatch does not support applyRefreshPolicy = true: add -SkipRefreshPolicy (Learn).'
    }
    if ($PSBoundParameters.ContainsKey('EffectiveDate') -and $SkipRefreshPolicy) {
        throw '-EffectiveDate only matters when the refresh policy is applied.'
    }
    if ($PSBoundParameters.ContainsKey('Timeout') -and ($Timeout.TotalHours * ($RetryCount + 1)) -gt 24) {
        throw "timeout $Timeout x $($RetryCount + 1) attempt(s) is over 24 hours: the total refresh duration, including retries, can't exceed 24 hours (Learn)."
    }
    $body = [ordered]@{ type = $Type; commitMode = $CommitMode }
    if ($PSBoundParameters.ContainsKey('MaxParallelism')) { $body.maxParallelism = $MaxParallelism }
    if ($RetryCount -gt 0) { $body.retryCount = $RetryCount }
    if ($PSBoundParameters.ContainsKey('Timeout')) { $body.timeout = '{0:00}:{1:00}:{2:00}' -f [math]::Floor($Timeout.TotalHours), $Timeout.Minutes, $Timeout.Seconds }
    if ($SkipRefreshPolicy) { $body.applyRefreshPolicy = $false }
    if ($PSBoundParameters.ContainsKey('EffectiveDate')) { $body.effectiveDate = $EffectiveDate.ToString('yyyy-MM-dd') }
    if ($Table) {
        $body.objects = @($(if ($Partition.Count) { $Partition | ForEach-Object { [ordered]@{ table = $Table; partition = $_ } } } else { [ordered]@{ table = $Table } }))
    }
    [pscustomobject]@{ Url = "groups/$WorkspaceId/datasets/$SemanticModelId/refreshes"; Body = $body }
}

function Get-PbiRefresh {
    <# .SYNOPSIS  The refresh history (newest first, -Top limits it) or one operation by request id. #>
    [CmdletBinding(DefaultParameterSetName = 'List')]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId, [Parameter(Mandatory)][string] $SemanticModelId,
        [Parameter(ParameterSetName = 'One', Mandatory)][string] $RequestId,
        [Parameter(ParameterSetName = 'List')][int] $Top
    )
    $base = "groups/$WorkspaceId/datasets/$SemanticModelId/refreshes"
    if ($PSCmdlet.ParameterSetName -eq 'One') { return Invoke-PbiApi -Method Get -Url "$base/$RequestId" }
    $r = Invoke-PbiApi -Method Get -Url $(if ($Top) { "$base`?`$top=$Top" } else { $base })
    @($(if ($r -and $r.PSObject.Properties['value']) { $r.value } else { $r }))
}

function Start-PbiEnhancedRefresh {
    <#
    .SYNOPSIS
        Sends the request and returns the request id. Learn: the id is the last segment of the Location header of the 202 response.
        Invoke-PowerBIRestMethod gives no headers here, so the id is read from the newest history entry: safe because the service
        runs one refresh at a time (a second request returns 400). With -WhatIf the request is returned and nothing is sent.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId, [Parameter(Mandatory)][string] $SemanticModelId,
        [ValidateSet('full', 'clearValues', 'calculate', 'dataOnly', 'automatic', 'defragment')][string] $Type = 'full',
        [ValidateSet('transactional', 'partialBatch')][string] $CommitMode = 'transactional',
        [string] $Table, [string[]] $Partition = @(), [switch] $SkipRefreshPolicy, [datetime] $EffectiveDate,
        [int] $MaxParallelism, [int] $RetryCount = 0, [timespan] $Timeout
    )
    $reqParams = @{} + $PSBoundParameters
    foreach ($k in 'WhatIf', 'Confirm', 'Verbose') { $reqParams.Remove($k) }
    $req = New-PbiRefreshRequest @reqParams
    $what = if ($req.Body.Contains('objects')) { "$(@($req.Body.objects).Count) object(s)" } else { 'the whole model' }
    if (-not $PSCmdlet.ShouldProcess("semantic model $SemanticModelId", "$($req.Body.type) refresh of $what")) {
        Write-Verbose ("POST {0} {1}" -f $req.Url, ($req.Body | ConvertTo-Json -Depth 6 -Compress))
        return $req
    }
    Invoke-PbiApi -Method Post -Url $req.Url -Body $req.Body | Out-Null
    $latest = @(Get-PbiRefresh -WorkspaceId $WorkspaceId -SemanticModelId $SemanticModelId -Top 1)[0]
    if (-not $latest -or -not $latest.requestId) { throw 'The refresh was accepted, but the history has no request id to follow.' }
    $latest.requestId
}

function Wait-PbiRefresh {
    <# .SYNOPSIS  Polls GET /refreshes/<id>. InProgress and NotStarted keep waiting; Completed returns; anything else throws. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId, [Parameter(Mandatory)][string] $SemanticModelId, [Parameter(Mandatory)][string] $RequestId,
        [int] $PollSeconds = 15, [int] $TimeoutSeconds = 3600
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ($true) {
        $op = Get-PbiRefresh -WorkspaceId $WorkspaceId -SemanticModelId $SemanticModelId -RequestId $RequestId
        if ($op.status -notin 'InProgress', 'NotStarted', 'Unknown') { break }
        if ((Get-Date) -gt $deadline) { throw "Refresh $RequestId still '$($op.status)' after $TimeoutSeconds seconds." }
        if ($PollSeconds -gt 0) { Start-Sleep -Seconds $PollSeconds }
    }
    if ($op.status -ne 'Completed') {
        $msgs = if ($op.PSObject.Properties['messages']) { (@($op.messages) | ForEach-Object { "$($_.code) $($_.message)" }) -join '; ' } else { '' }
        $failed = @($op.objects) | Where-Object { $_ -and $_.status -ne 'Completed' } | ForEach-Object { "$($_.table)/$($_.partition)=$($_.status)" }
        throw "Refresh $RequestId ended '$($op.status)'. $msgs $($failed -join ', ')".Trim()
    }
    $op
}

function Stop-PbiRefresh {
    <# .SYNOPSIS  Cancels an in-progress enhanced refresh (DELETE). Standard (portal, scheduled) refreshes can't be cancelled this way. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][string] $WorkspaceId, [Parameter(Mandatory)][string] $SemanticModelId, [Parameter(Mandatory)][string] $RequestId)
    if ($PSCmdlet.ShouldProcess("refresh $RequestId", 'cancel')) {
        Invoke-PbiApi -Method Delete -Url "groups/$WorkspaceId/datasets/$SemanticModelId/refreshes/$RequestId" | Out-Null
    }
}

Export-ModuleMember -Function New-PbiRefreshRequest, Start-PbiEnhancedRefresh, Get-PbiRefresh, Wait-PbiRefresh, Stop-PbiRefresh
