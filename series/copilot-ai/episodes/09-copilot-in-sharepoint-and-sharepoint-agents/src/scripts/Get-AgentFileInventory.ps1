<#
.SYNOPSIS
  Lists the .agent files you can see in the tenant (search) and writes them to a CSV for `python -m agentfiles`.

.DESCRIPTION
  Learn (Monitor agent usage in SharePoint): "By searching for *.agent, you find all agent files within the selected
  scope. The results only include agent files that you have permission to access." So this is a search, run as the
  signed-in user: it is not an admin-wide inventory. For that Learn points to the Agent Insights report
  (SharePoint Advanced Management or a Microsoft Copilot licence) and the agent registry.
  Read-only: it only calls Submit-PnPSearchQuery.

  Needs the tenant: PnP.PowerShell 3.x and your own Entra app registration (-ClientId), as in episode 3.
  The managed properties come from the SharePoint managed-property reference (ViewsLifeTime, ViewsRecent, ...); the first
  real run shows whether every one is retrievable in your tenant.

.EXAMPLE
  ./Get-AgentFileInventory.ps1 -TenantUrl https://<tenant>.sharepoint.com -ClientId <app id> -OutFile ./agent-files.csv
  ./Get-AgentFileInventory.ps1 -TenantUrl https://<tenant>.sharepoint.com -ClientId <app id> `
      -SiteUrl https://<tenant>.sharepoint.com/sites/contoso-vmo -OutFile ./agent-files.csv
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^https://[a-z0-9-]+\.sharepoint\.com/?$')][string]$TenantUrl,
    [Parameter(Mandatory)][string]$ClientId,
    [string]$SiteUrl,
    [string]$OutFile = './agent-files.csv'
)

$ErrorActionPreference = 'Stop'
$TenantUrl = $TenantUrl.TrimEnd('/')

$columns = 'Title', 'Path', 'Author', 'Created', 'LastModifiedTime', 'SPSiteUrl', 'SiteTitle',
           'ViewsLifeTime', 'ViewsRecent', 'ViewsLifeTimeUniqueUsers'

# KQL: the managed property FileExtension; optionally limited to one site with Path.
$query = 'FileExtension:agent'
if ($SiteUrl) { $query += ' Path:"' + $SiteUrl.TrimEnd('/') + '"' }

Connect-PnPOnline -Url $TenantUrl -Interactive -ClientId $ClientId

$result = Submit-PnPSearchQuery -Query $query -All -SelectProperties $columns
# Depending on the PnP.PowerShell version the rows come back in .ResultRows or directly.
$rows = if ($null -ne $result -and $result.PSObject.Properties['ResultRows']) { $result.ResultRows } else { $result }

$records = foreach ($row in @($rows)) {
    $o = [ordered]@{}
    foreach ($c in $columns) { $o[$c] = "$($row[$c])" }
    [pscustomobject]$o
}
if (-not $records) {
    # Export-Csv writes nothing for an empty list: write the header so the Python side still reads the file.
    Set-Content -Path $OutFile -Value ($columns -join ',') -Encoding utf8
    Write-Host "No .agent files visible to you. Query: $query"
} else {
    @($records) | Export-Csv -Path $OutFile -NoTypeInformation -Encoding utf8
    Write-Host "Wrote $(@($records).Count) row(s) to $OutFile. Query: $query"
}
