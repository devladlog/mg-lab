<#
.SYNOPSIS
  Read-only snapshot of the settings that decide what Microsoft 365 Copilot can reach and what is protected.
.DESCRIPTION
  Writes one JSON file for `python -m copilot_governance`. Needs the tenant and three connections made BEFORE you run it
  (the script never signs in and never changes anything):
    Connect-ExchangeOnline          -> Get-AdminAuditLogConfig
    Connect-IPPSSession             -> Get-Label, Get-LabelPolicy, Get-DlpCompliancePolicy, Get-DlpComplianceRule
    Connect-SPOService -Url https://<tenant>-admin.sharepoint.com -> Get-SPOTenant, Get-SPOSite
  Each section is collected on its own: when one fails (missing role, module not connected) its error is recorded under
  "errors" and the checks report that section as "not collected" instead of passing it.
  Get-SPOSite gotcha (Learn): with -Limit or -Filter, properties such as SensitivityLabel and SharingCapability are NOT
  populated. So the site list is read without them and then every site is read again by -Identity (up to -MaxSites).
#>
[CmdletBinding()]
param(
    [string]$OutFile = './copilot-governance-snapshot.json',
    [ValidateRange(1, 500)][int]$MaxSites = 50
)

function Get-SectionSafe {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][scriptblock]$Script, [hashtable]$Errors)
    try { , @(& $Script) }
    catch { $Errors[$Name] = $_.Exception.Message; $null }
}

function New-CopilotGovernanceSnapshot {
    [CmdletBinding()]
    param([int]$MaxSites = 50)
    $errors = @{}
    $snap = [ordered]@{ collectedAt = (Get-Date).ToUniversalTime().ToString('o') }

    $audit = Get-SectionSafe -Name 'auditLog' -Errors $errors -Script {
        Get-AdminAuditLogConfig | Select-Object UnifiedAuditLogIngestionEnabled
    }
    $snap.auditLog = if ($audit) { $audit[0] } else { $null }

    $snap.labels = Get-SectionSafe -Name 'labels' -Errors $errors -Script {
        Get-Label | Select-Object Name, DisplayName, Guid, Disabled, ContentType
    }
    $snap.labelPolicies = Get-SectionSafe -Name 'labelPolicies' -Errors $errors -Script {
        Get-LabelPolicy | Select-Object Name, Enabled, Labels
    }
    $snap.dlpPolicies = Get-SectionSafe -Name 'dlpPolicies' -Errors $errors -Script {
        Get-DlpCompliancePolicy | ForEach-Object {
            $p = $_
            [pscustomobject]@{
                Name = $p.Name; Mode = [string]$p.Mode; Enabled = $p.Enabled
                EnforcementPlanes = $p.EnforcementPlanes; Locations = $p.Locations
                Rules = @(Get-DlpComplianceRule -Policy $p.Name | Select-Object Name, RestrictAccess)
            }
        }
    }

    $tenant = Get-SectionSafe -Name 'sharePointTenant' -Errors $errors -Script {
        Get-SPOTenant | Select-Object SharingCapability, ShowEveryoneExceptExternalUsersClaim,
            AllowEveryoneExceptExternalUsersClaimInPrivateSite, DefaultSharingLinkType
    }
    $snap.sharePointTenant = if ($tenant) { $tenant[0] } else { $null }

    $snap.sites = Get-SectionSafe -Name 'sites' -Errors $errors -Script {
        $urls = @(Get-SPOSite | Select-Object -First $MaxSites -ExpandProperty Url)
        foreach ($u in $urls) {
            Get-SPOSite -Identity $u | Select-Object Url, Title, Template, SharingCapability, SensitivityLabel,
                RestrictContentOrgWideSearch, RestrictedAccessControl
        }
    }
    $snap.errors = $errors
    [pscustomobject]$snap
}

# Run only when executed, not when dot-sourced by the tests.
if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    $snapshot = New-CopilotGovernanceSnapshot -MaxSites $MaxSites
    $snapshot | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutFile -Encoding utf8
    $bad = @($snapshot.errors.Keys)
    Write-Host ("Snapshot written to {0}; sections not collected: {1}" -f $OutFile, $(if ($bad.Count) { $bad -join ', ' } else { 'none' }))
}
