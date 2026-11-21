#Requires -RunAsAdministrator
<#
.SYNOPSIS  Shuts down the MG Lab VMs cleanly (members first, DC last) to free RAM. Start again with Start-MGLab.ps1
           or Start-VM. -Start starts them all again (DC first).
#>
param([string]$Config = (Join-Path $PSScriptRoot 'lab.config.psd1'), [switch]$Start)
$cfg = Import-PowerShellDataFile -Path $Config
$dc = @($cfg.VMs | Where-Object Role -eq 'DC').Name
$others = @($cfg.VMs | Where-Object Role -ne 'DC').Name
if ($Start) {
    foreach ($n in $dc + $others) { if (Get-VM $n -ErrorAction SilentlyContinue) { Start-VM $n; if ($dc -contains $n) { Start-Sleep 60 } } }
} else {
    foreach ($n in $others + $dc) { if ((Get-VM $n -ErrorAction SilentlyContinue).State -eq 'Running') { Stop-VM $n } }
}
Get-VM | Where-Object { $cfg.VMs.Name -contains $_.Name } | Format-Table Name, State, @{n = 'RAM GB'; e = { [math]::Round($_.MemoryAssigned / 1GB, 1) } } -AutoSize
