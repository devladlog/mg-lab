<#
.SYNOPSIS
  Starts the MG Lab VMs (domain controller first) and waits until each answers. Needs Hyper-V rights: run it elevated
  or as a member of "Hyper-V Administrators" (Setup-RecordingLaptop.ps1 adds you). -Stop shuts them down, DC last.
#>
param([string[]] $Name, [switch] $Stop)
$ErrorActionPreference = 'Stop'
$vms = Get-VM -Name 'CON-*' | Where-Object { -not $Name -or $Name -contains $_.Name }
$dc = $vms | Where-Object Name -like '*-DC*'
$others = $vms | Where-Object Name -notlike '*-DC*'
if ($Stop) {
    foreach ($v in @($others) + @($dc)) { if ($v.State -eq 'Running') { Write-Host "Stopping $($v.Name)"; Stop-VM -Name $v.Name } }
    return
}
foreach ($v in @($dc) + @($others)) {
    if (-not $v) { continue }
    if ($v.State -ne 'Running') { Write-Host "Starting $($v.Name)"; Start-VM -Name $v.Name }
    $end = (Get-Date).AddMinutes(5)
    do {
        $hb = (Get-VMIntegrationService -VMName $v.Name -Name Heartbeat).PrimaryStatusDescription
        if ($hb -eq 'OK') { break }
        Start-Sleep 5
    } while ((Get-Date) -lt $end)
    Write-Host ("  {0,-12} {1,-8} heartbeat {2}" -f $v.Name, (Get-VM $v.Name).State, $hb)
}
