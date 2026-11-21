<#
.SYNOPSIS
  Tear-down for New-EmbedServicePrincipal.ps1: removes the Entra app (and with it the service principal and its secret)
  and the security group. The workspace role goes away with the service principal.
  Needs a tenant (Connect-MgGraph).
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [string] $AppName = 'Contoso Embed (Lab)',
    [string] $GroupName = 'Contoso Embed SPs (Lab)'
)
$ErrorActionPreference = 'Stop'
Connect-MgGraph -Scopes 'Application.ReadWrite.All', 'Group.ReadWrite.All' -NoWelcome

foreach ($app in Get-MgApplication -Filter "displayName eq '$AppName'") {
    if ($PSCmdlet.ShouldProcess("app $AppName ($($app.AppId))", 'Remove')) { Remove-MgApplication -ApplicationId $app.Id }
}
foreach ($group in Get-MgGroup -Filter "displayName eq '$GroupName'") {
    if ($PSCmdlet.ShouldProcess("group $GroupName ($($group.Id))", 'Remove')) { Remove-MgGroup -GroupId $group.Id }
}
