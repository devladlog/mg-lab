#Requires -Version 7.2
<#
.SYNOPSIS
    Runner for DEVLADLOG Microsoft 365 #13 (Microsoft 365 Apps deployment).
.EXAMPLE
    ./Invoke-AppsDeploy.ps1 -BuildXml -OutFile ./configuration.xml            # offline: config -> ODT configuration.xml
    ./Invoke-AppsDeploy.ps1 -ValidateXml ./configuration.xml                  # offline: check any ODT file against Learn's values
    ./Invoke-AppsDeploy.ps1 -Install -OdtPath C:\ODT\setup.exe -WhatIf         # Windows client, local administrator
    ./Invoke-AppsDeploy.ps1 -Inventory                                        # Windows client: what is installed, vs the published builds
    ./Invoke-AppsDeploy.ps1 -PublishIntune -WhatIf                            # Graph beta, DeviceManagementApps.ReadWrite.All
    ./Invoke-AppsDeploy.ps1 -ActivationAudit                                  # Graph v1.0, Reports.Read.All (or -ReportFile a saved CSV)
#>
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSAvoidUsingWriteHost', '', Justification = 'Console runner')]
[Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSReviewUnusedParameter', 'OutFile', Justification = 'Used by Write-Out')]
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ConfigFile = (Join-Path $PSScriptRoot 'apps.json'),
    [switch]$BuildXml,
    [ValidateSet('Install', 'Download')][string]$Mode = 'Install',
    [string]$SourcePath,
    [string]$ValidateXml,
    [switch]$Install,
    [string]$OdtPath,
    [switch]$Inventory,
    [string]$ReleasesFile,
    [switch]$PublishIntune,
    [switch]$ActivationAudit,
    [string]$ReportFile,
    [string]$OutFile,
    [datetimeoffset]$Now = [datetimeoffset]::UtcNow
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'AppsDeploy/AppsDeploy.psd1') -Force

function Write-Out([string]$Text) { if ($OutFile) { Set-Content -Path $OutFile -Value $Text -Encoding utf8; Write-Host "Wrote $OutFile" } else { $Text } }

if ($ValidateXml) {
    $problems = @(Test-ADOdtXml -Xml (Get-Content $ValidateXml -Raw))
    if ($problems.Count) { $problems | ForEach-Object { Write-Host "INVALID: $_" -ForegroundColor Red }; exit 1 }
    Write-Host "OK: $ValidateXml follows the documented values."; return
}

$config = Get-ADConfig -Path $ConfigFile

if ($BuildXml) {
    $xml = New-ADOdtXml -Config $config -Mode $Mode -SourcePath $SourcePath
    $problems = @(Test-ADOdtXml -Xml $xml)
    if ($problems.Count) { throw "Generated XML is invalid: $($problems -join ' ')" }
    Write-Out $xml
}
elseif ($Install) {
    if (-not $OdtPath) { throw '-OdtPath (the path to setup.exe from the Office Deployment Tool) is required with -Install.' }
    Install-ADOffice -Config $config -OdtPath $OdtPath -Mode $Mode -SourcePath $SourcePath | Format-List | Out-String -Width 200 | Write-Host
}
elseif ($Inventory) {
    $client = Get-ADOfficeClient
    $releases = @(Get-ADReleaseChannel -Path $ReleasesFile)
    $channel = Resolve-ADChannel -Url $(if ($client.UpdateChannel) { $client.UpdateChannel } else { $client.CdnBaseUrl }) -Releases $releases
    $info = $client | Select-Object *, @{ n = 'Channel'; e = { if ($channel) { $channel.name } else { 'unknown' } } }
    $info | Format-List | Out-String -Width 200 | Write-Host
    $f = @(Get-ADClientFinding -Client $client -Config $config -Releases $releases)
    Write-Out (ConvertTo-ADMarkdown -Title "Microsoft 365 Apps client check: $($client.ComputerName)" -Findings $f -Asof $Now.ToString('u'))
}
elseif ($PublishIntune) {
    Set-ADOfficeSuiteApp -Config $config | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
}
elseif ($ActivationAudit) {
    $rows = @(Get-ADActivationReport -Path $ReportFile)
    $f = @(Get-ADActivationFinding -Rows $rows -Config $config -Now $Now)
    $note = "$($rows.Count) activation row(s) in the report (one per user and product)."
    Write-Out (ConvertTo-ADMarkdown -Title 'Microsoft 365 Apps activation audit' -Findings $f -Asof $Now.ToString('u') -Notes @($note))
}
else { Get-Help $PSCommandPath -Examples | Out-String | Write-Host }
