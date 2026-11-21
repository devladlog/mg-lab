#requires -Version 7.2
<#
.SYNOPSIS  Contoso Zero Trust, identity and device half (DEVLADLOG Deep Dive #9). Needs the lab tenant.
.DESCRIPTION
  1. Finds or creates two groups: pilot (who the policies target) and break-glass (who they never touch).
  2. Resolves the built-in phishing-resistant authentication strength by name.
  3. Creates or updates three Conditional Access policies, all in REPORT-ONLY.
  4. Creates the Intune Windows compliance policy and assigns it to the pilot group.
  Add -Enforce only after the report-only results look right. -WhatIf shows what would be written.
  Connect first (as the lab Global Administrator):
    Connect-MgGraph -Scopes Policy.ReadWrite.ConditionalAccess,Policy.Read.All,Group.ReadWrite.All,DeviceManagementConfiguration.ReadWrite.All
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$PilotGroupName = 'ct-zt-pilot',
    [string]$BreakGlassGroupName = 'ct-zt-breakglass',
    [switch]$Enforce
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Module ZeroTrust)) { Import-Module (Join-Path $PSScriptRoot 'ZeroTrust.psm1') }
$root = Split-Path $PSScriptRoot -Parent

$pilot = Initialize-LabGroup -DisplayName $PilotGroupName -WhatIf:$WhatIfPreference
$breakGlass = Initialize-LabGroup -DisplayName $BreakGlassGroupName -Description 'Emergency access accounts: excluded from every policy' -WhatIf:$WhatIfPreference
$strength = Resolve-AuthStrengthId

# Under -WhatIf a group that does not exist yet has no id: use a clearly fake one so the dry run still validates the templates.
$values = @{
    pilotGroupId                = if ($pilot) { $pilot } else { '00000000-0000-0000-0000-000000000001' }
    breakGlassGroupId           = if ($breakGlass) { $breakGlass } else { '00000000-0000-0000-0000-000000000002' }
    phishingResistantStrengthId = $strength
}

Get-ChildItem (Join-Path $root 'entra/policies') -Filter ct*.json | Sort-Object Name | ForEach-Object {
    Publish-CaPolicy -TemplatePath $_.FullName -Values $values -Enforce:$Enforce -WhatIf:$WhatIfPreference
}
Publish-CompliancePolicy -Path (Join-Path $root 'intune/windows-compliance.json') -GroupId $values.pilotGroupId -WhatIf:$WhatIfPreference
