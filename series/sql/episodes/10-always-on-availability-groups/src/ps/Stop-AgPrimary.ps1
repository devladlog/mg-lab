<#
.SYNOPSIS
    The automatic-failover trigger for the demo: stop the SQL Server service on the current primary, wait, start it
    again. Run it from the laptop or CON-SRV02 as the lab Administrator while `ag_lab.py --watch` is timing the
    failover. The default instance's service is MSSQLSERVER. The restarted instance comes back as a secondary.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)] [string] $Node,
    [int] $SecondsDown = 45,
    [string] $ServiceName = 'MSSQLSERVER'
)

$ErrorActionPreference = 'Stop'

if ($PSCmdlet.ShouldProcess($Node, "stop $ServiceName")) {
    Invoke-Command -ComputerName $Node -ArgumentList $ServiceName -ScriptBlock {
        param($name)
        Stop-Service -Name $name -Force
    }
    Write-Host ("{0:HH:mm:ss}  stopped {1} on {2}; waiting {3} s" -f (Get-Date), $ServiceName, $Node, $SecondsDown)
    Start-Sleep -Seconds $SecondsDown
}

if ($PSCmdlet.ShouldProcess($Node, "start $ServiceName")) {
    Invoke-Command -ComputerName $Node -ArgumentList $ServiceName -ScriptBlock {
        param($name)
        Start-Service -Name $name
    }
    Write-Host ("{0:HH:mm:ss}  started {1} on {2}" -f (Get-Date), $ServiceName, $Node)
}
