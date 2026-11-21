<#
.SYNOPSIS
  Adds test requests to the IT Requests list (and removes them again) with PnP.PowerShell batching.
.DESCRIPTION
  Titles start with "[TEST] seed" so episode 1's intake flow ignores them (its trigger condition skips [test]).
  A share of the items are Done with DoneOn more than 30 days ago (the ones the housekeeping flow archives), 10 % are Done
  recently, the rest are New or Triaged. Connect first (Connect-PnPOnline -Url <site> -Interactive -ClientId <app id>);
  this script uses the current connection. List needs the columns Status (choice: New, Triaged, Done, Archived) and
  DoneOn (date and time).
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ListName = 'IT Requests',
    [ValidateRange(1, 20000)][int]$Count = 1000,
    [ValidateRange(0, 0.9)][double]$DoneOldFraction = 0.4,
    [ValidateRange(1, 500)][int]$BatchSize = 100,
    [datetime]$Now = (Get-Date).ToUniversalTime(),
    [switch]$Cleanup
)
$ErrorActionPreference = 'Stop'
$prefix = '[TEST] seed '

if ($Cleanup) {
    $ids = Get-PnPListItem -List $ListName -PageSize 500 -Fields 'Title' |
        Where-Object { ([string]$_.FieldValues['Title']).StartsWith($prefix) } | ForEach-Object { $_.Id }
    $batch = New-PnPBatch
    $n = 0
    foreach ($id in $ids) {
        Remove-PnPListItem -List $ListName -Identity $id -Recycle -Batch $batch
        if (++$n % $BatchSize -eq 0) { Invoke-PnPBatch -Batch $batch; $batch = New-PnPBatch }
    }
    if ($n % $BatchSize -ne 0) { Invoke-PnPBatch -Batch $batch }
    Write-Host "Removed $n seeded items from '$ListName'"
    return
}

$old = [int][math]::Floor($Count * $DoneOldFraction)
$recent = [int][math]::Floor($Count * 0.1)
$batch = New-PnPBatch
for ($i = 1; $i -le $Count; $i++) {
    if ($i -le $old) { $status = 'Done'; $doneOn = $Now.AddDays(-(31 + $i % 60)) }
    elseif ($i -le $old + $recent) { $status = 'Done'; $doneOn = $Now.AddDays(-(1 + $i % 20)) }
    else { $status = if ($i % 2) { 'Triaged' } else { 'New' }; $doneOn = $null }
    $values = @{ Title = "$prefix$i"; Status = $status }
    if ($doneOn) { $values['DoneOn'] = $doneOn }
    if ($PSCmdlet.ShouldProcess("$ListName #$i", 'Add item')) { Add-PnPListItem -List $ListName -Values $values -Batch $batch | Out-Null }
    if ($i % $BatchSize -eq 0) { Invoke-PnPBatch -Batch $batch; $batch = New-PnPBatch }
}
if ($Count % $BatchSize -ne 0) { Invoke-PnPBatch -Batch $batch }
Write-Host "Added $Count items to '$ListName': $old Done long ago, $recent Done recently, $($Count - $old - $recent) open"
