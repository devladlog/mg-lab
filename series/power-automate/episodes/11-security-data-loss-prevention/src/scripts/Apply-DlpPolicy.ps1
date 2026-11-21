<#
.SYNOPSIS
  Makes an existing data policy match a policy file: sets the default group and moves connectors between
  Business (Confidential), Non-business (General) and Blocked.

.DESCRIPTION
  The policy file has the shape Get-DlpPolicy returns (displayName, defaultConnectorsClassification,
  connectorGroups[].classification / connectors[].id, name, type). Only what the file lists is touched:
  connectors it doesn't mention keep their group.

  Needs Windows PowerShell 5.1 and the Microsoft.PowerApps.Administration.PowerShell module (Learn: the
  module uses .NET Framework and doesn't run on PowerShell 7), and a session signed in with
  Add-PowerAppsAccount as a Power Platform administrator. Create the policy once in the Power Platform
  admin center (Policies > Data policies > New policy); this script keeps its classification in Git.

  Learn: Get-DlpPolicy doesn't return connectors that sit in the default group and were never moved, so a
  connector that is not in the policy's lists is treated as being in its default group.

.EXAMPLE
  .\Apply-DlpPolicy.ps1 -PolicyFile ..\policy\it-dev.json -WhatIf
  .\Apply-DlpPolicy.ps1 -PolicyFile ..\policy\it-dev.json
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)] [string]$PolicyFile,
    # Policy GUID (the "name" Get-DlpPolicy returns). Default: the policy whose displayName matches the file.
    [string]$PolicyName
)
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'

foreach ($cmd in 'Get-DlpPolicy', 'Add-ConnectorsToPolicy', 'Set-DlpPolicy') {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "$cmd not found. Use Windows PowerShell 5.1, run Install-Module Microsoft.PowerApps.Administration.PowerShell, then Add-PowerAppsAccount."
    }
}
$Valid = @('General', 'Confidential', 'Blocked')   # Non-business, Business, Blocked (Learn: Add-ConnectorsToPolicy -Classification)
$ConnectorType = 'providers/Microsoft.PowerApps/apis'

function Get-ShortId([string]$Id) { return ($Id.TrimEnd('/') -split '/')[-1].ToLowerInvariant() }

$want = Get-Content -Raw -LiteralPath $PolicyFile | ConvertFrom-Json
if ($null -eq $want.PSObject.Properties['displayName']) { throw "$PolicyFile has no displayName" }
$desiredDefault = if ($null -ne $want.PSObject.Properties['defaultConnectorsClassification']) { $want.defaultConnectorsClassification } else { $null }
$desired = [ordered]@{}
foreach ($group in $want.connectorGroups) {
    if ($Valid -notcontains $group.classification) { throw "Unknown classification '$($group.classification)' in $PolicyFile (use General, Confidential or Blocked)" }
    foreach ($c in $group.connectors) {
        $short = Get-ShortId $c.id
        if ($desired.Contains($short)) { throw "Connector $short is listed in two groups in $PolicyFile" }
        $type = if ($null -ne $c.PSObject.Properties['type']) { $c.type } else { $ConnectorType }
        $name = if ($null -ne $c.PSObject.Properties['name']) { $c.name } else { $short }
        $desired[$short] = [pscustomobject]@{ id = $c.id; name = $name; type = $type; classification = $group.classification }
    }
}
if ($null -ne $desiredDefault -and $Valid -notcontains $desiredDefault) { throw "Unknown defaultConnectorsClassification '$desiredDefault'" }

function Find-Policy {
    $all = @((Get-DlpPolicy).value)
    if ($PolicyName) { $hit = @($all | Where-Object { $_.name -eq $PolicyName }) }
    else { $hit = @($all | Where-Object { $_.displayName -eq $want.displayName }) }
    if ($hit.Count -eq 0) { throw "No data policy named '$($want.displayName)' ($PolicyName). Create it in the admin center first, then run this again." }
    if ($hit.Count -gt 1) { throw "More than one policy is named '$($want.displayName)'. Pass -PolicyName with the GUID." }
    return $hit[0]
}

$policy = Find-Policy
$policyDefault = $policy.defaultConnectorsClassification
$effectiveDefault = $policyDefault

# 1. default group (done first: it decides which group the unlisted connectors are in)
if ($desiredDefault -and $desiredDefault -ne $policyDefault) {
    Write-Output ("DEFAULT  {0} -> {1}" -f $policyDefault, $desiredDefault)
    $effectiveDefault = $desiredDefault
    if ($PSCmdlet.ShouldProcess("policy '$($policy.displayName)'", "Set the default group to $desiredDefault")) {
        $policy.defaultConnectorsClassification = $desiredDefault
        Set-DlpPolicy -PolicyName $policy.name -UpdatedPolicy $policy | Out-Null
        $policy = Find-Policy          # moves below must start from what the service now holds
    }
}

# 2. connectors
$current = @{}
foreach ($group in @($policy.connectorGroups)) {
    foreach ($c in @($group.connectors)) { $current[(Get-ShortId $c.id)] = $group.classification }
}
$moves = @{}
foreach ($short in $desired.Keys) {
    $now = if ($current.ContainsKey($short)) { $current[$short] } else { $effectiveDefault }
    $to = $desired[$short].classification
    if ($now -ne $to) {
        Write-Output ("MOVE     {0}  {1} -> {2}" -f $desired[$short].name, $now, $to)
        if (-not $moves.ContainsKey($to)) { $moves[$to] = @() }
        $moves[$to] += $desired[$short]
    }
}
foreach ($cls in @($moves.Keys)) {
    $objects = @($moves[$cls] | ForEach-Object { [pscustomobject]@{ id = $_.id; name = $_.name; type = $_.type } })
    if ($PSCmdlet.ShouldProcess("policy '$($policy.displayName)'", "Move $($objects.Count) connector(s) to $cls")) {
        Add-ConnectorsToPolicy -PolicyName $policy.name -Classification $cls -Connectors $objects | Out-Null
    }
}
$moved = 0
foreach ($v in $moves.Values) { $moved += @($v).Count }
if ($moved -eq 0 -and $effectiveDefault -eq $policyDefault) { Write-Output "Nothing to change: '$($policy.displayName)' already matches $PolicyFile." }
