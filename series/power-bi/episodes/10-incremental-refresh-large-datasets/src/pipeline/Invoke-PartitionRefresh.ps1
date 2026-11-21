#Requires -Version 7.2
<#
.SYNOPSIS
    Refreshes named partitions of an incremental refresh table (a back-dated correction), or the whole table with the policy
    applied for a chosen day. -WhatIf prints the request and sends nothing.

.EXAMPLE
    # reload March 2023 only (partition names: look them up in SSMS, or python tools/ir_partitions.py)
    ./Invoke-PartitionRefresh.ps1 -WorkspaceId $ws -SemanticModelId $m -Table Sales -Partition 2023Q103 -SkipRefreshPolicy -WhatIf
.EXAMPLE
    # run the policy as if it were 1 December 2026 (partitions roll forward as they would on that day)
    ./Invoke-PartitionRefresh.ps1 -WorkspaceId $ws -SemanticModelId $m -Table Sales -EffectiveDate 2026-12-01 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)][string] $WorkspaceId,
    [Parameter(Mandatory)][string] $SemanticModelId,
    [Parameter(Mandatory)][string] $Table,
    [string[]] $Partition = @(),
    [switch] $SkipRefreshPolicy,
    [datetime] $EffectiveDate,
    [switch] $NoWait
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'PbiRefresh' 'PbiRefresh.psd1')
$start = @{ WorkspaceId = $WorkspaceId; SemanticModelId = $SemanticModelId; Table = $Table; Partition = $Partition }
if ($SkipRefreshPolicy) { $start.SkipRefreshPolicy = $true }
if ($PSBoundParameters.ContainsKey('EffectiveDate')) { $start.EffectiveDate = $EffectiveDate }
$id = Start-PbiEnhancedRefresh @start -WhatIf:$WhatIfPreference -Confirm:$false
if ($WhatIfPreference) { Write-Host ("WhatIf: POST {0} {1}" -f $id.Url, ($id.Body | ConvertTo-Json -Depth 6 -Compress)); return }
Write-Host "Refresh request $id"
if (-not $NoWait) {
    $op = Wait-PbiRefresh -WorkspaceId $WorkspaceId -SemanticModelId $SemanticModelId -RequestId $id
    Write-Host "Refresh $($op.status)"
    @($op.objects) | ForEach-Object { Write-Host ("  {0}/{1}: {2}" -f $_.table, $_.partition, $_.status) }
}
