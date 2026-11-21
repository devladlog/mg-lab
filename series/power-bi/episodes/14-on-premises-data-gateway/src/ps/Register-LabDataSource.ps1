#requires -Version 7.2
<#
.SYNOPSIS
    Creates the lab SQL Server data source on the gateway (credentials encrypted for the gateway), and optionally binds a semantic model to it.
.DESCRIPTION
    1. reads ../gateway/datasource.json (name, server, database, SQL login)
    2. checks that queries/sales-by-store.pq uses exactly that server and database (Learn: the link is server + database, case-sensitive)
    3. creates the data source with Gateways - Create Datasource (credentials encrypted by the Power BI SDK, see src/GatewayCredential)
    4. with -WorkspaceId and -DatasetId: shows the model's data sources, binds it (Bind To Gateway) and shows them again
    -WhatIf sends nothing. Needs Connect-PowerBIServiceAccount first, as a gateway admin. The password is asked for, never a parameter value in plain text.
    Needs a tenant and a gateway.
.EXAMPLE
    Connect-PowerBIServiceAccount
    ./Register-LabDataSource.ps1 -GatewayName contoso-lab-gw -WhatIf
#>
[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory)][string] $GatewayName,
    [string] $WorkspaceId,
    [string] $DatasetId,
    [securestring] $Password = (Read-Host -AsSecureString "Password of the SQL login"),
    [string] $ToolPath = (Join-Path $PSScriptRoot '..' 'GatewayCredential' 'bin' 'Debug' 'net8.0' 'gateway-credential.dll')
)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'GatewayOps' 'GatewayOps.psd1')

$def = Get-Content -Raw (Join-Path $PSScriptRoot '..' 'gateway' 'datasource.json') | ConvertFrom-Json
$query = Join-Path $PSScriptRoot '..' 'queries' 'sales-by-store.pq'

$check = @(Test-DataSourceMatch -QueryPath $query -GatewayDataSource ([pscustomobject]@{ Type = $def.type; Server = $def.server; Database = $def.database }))
$check | ForEach-Object { Write-Host ('{0} {1}: {2}' -f $_.Rule, $_.Severity, $_.Message) }
if ($check | Where-Object Severity -eq 'Error') { throw 'The query and datasource.json disagree: fix one of them first.' }

New-GatewayDataSource -GatewayName $GatewayName -Name $def.name -Server $def.server -Database $def.database `
    -Username $def.username -Password $Password -PrivacyLevel $def.privacyLevel -ToolPath $ToolPath -WhatIf:$WhatIfPreference -Confirm:$false

$gw = Get-GatewayCluster -Name $GatewayName
Write-Host "Data sources on '$GatewayName':"
Get-GatewayDataSource -GatewayId $gw.Id | Format-Table Name, Type, Server, Database, CredentialType -AutoSize | Out-String -Width 160 | Write-Host

if ($WorkspaceId -and $DatasetId) {
    Write-Host 'Model before:'; Get-DatasetGatewayInfo -WorkspaceId $WorkspaceId -DatasetId $DatasetId | Format-Table Type, Server, Database, IsBound | Out-String -Width 160 | Write-Host
    Set-DatasetGateway -WorkspaceId $WorkspaceId -DatasetId $DatasetId -GatewayId $gw.Id -WhatIf:$WhatIfPreference -Confirm:$false
    Write-Host 'Model after:'; Get-DatasetGatewayInfo -WorkspaceId $WorkspaceId -DatasetId $DatasetId | Format-Table Type, Server, Database, IsBound | Out-String -Width 160 | Write-Host
}
