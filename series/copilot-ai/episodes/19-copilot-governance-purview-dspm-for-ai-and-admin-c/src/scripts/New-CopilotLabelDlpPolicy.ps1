<#
.SYNOPSIS
  Creates a DLP policy for the "Microsoft Copilot, Copilot Chat, and Copilot Cowork" location that stops Copilot from
  processing items with the chosen sensitivity labels. Created in SIMULATION mode by default.
.DESCRIPTION
  Follows the Security & Compliance PowerShell example on Learn (New-DlpCompliancePolicy, Example 4):
    -Locations with the Copilot location id, -EnforcementPlanes CopilotExperiences,
    a rule with the label condition and -RestrictAccess @(@{setting='ExcludeContentProcessing'; value='Block'}).
  Needs the tenant: Connect-IPPSSession first, with a role that may edit Copilot DLP policies (Learn lists, among others,
  Purview Data Security AI Admin, Compliance Administrator, Information Protection Admin, Global Administrator).
  Nothing is created unless you pass -Apply; without it the script prints the exact policy and rule it would create.
  Learn: updates can take up to four hours to reach Copilot; simulation mode is available for Microsoft 365 Copilot.
.EXAMPLE
  ./New-CopilotLabelDlpPolicy.ps1 -LabelName 'Highly Confidential'            # prints the plan
  ./New-CopilotLabelDlpPolicy.ps1 -LabelName 'Highly Confidential' -Apply     # creates it in simulation mode
  ./New-CopilotLabelDlpPolicy.ps1 -LabelName 'Highly Confidential' -Apply -Mode Enable
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string[]]$LabelName,
    [string]$PolicyName = 'MG Lab - Copilot: block labelled content',
    [ValidateSet('TestWithoutNotifications', 'TestWithNotifications', 'Enable', 'Disable')][string]$Mode = 'TestWithoutNotifications',
    [switch]$Apply
)

$CopilotLocationId = '470f2276-e011-4e9d-a6ec-20768be3a4b0'   # Learn: New-DlpCompliancePolicy -Locations

function Resolve-LabelGuids {
    param([string[]]$Names)
    foreach ($n in $Names) {
        $hit = @(Get-Label | Where-Object { $_.DisplayName -eq $n -or $_.Name -eq $n })
        if ($hit.Count -ne 1) { throw "Label '$n' matched $($hit.Count) labels; use the exact display name or name." }
        [string]$hit[0].Guid
    }
}

function New-CopilotDlpPlan {
    param([string]$PolicyName, [string[]]$LabelGuids, [string]$Mode)
    $locations = ConvertTo-Json -Compress -Depth 6 -InputObject @(
        [ordered]@{ Workload = 'Applications'; Location = $CopilotLocationId; Inclusions = @(@{ Type = 'Tenant'; Identity = 'All' }) })
    $labels = @($LabelGuids | ForEach-Object { @{ name = $_; type = 'Sensitivity' } })
    $advanced = @{
        Version   = '1.0'
        Condition = @{
            Operator      = 'And'
            SubConditions = @(@{
                    ConditionName = 'ContentContainsSensitiveInformation'
                    Value         = @(@{ groups = @(@{ Operator = 'Or'; labels = $labels; name = 'Default' }) })
                })
        }
    } | ConvertTo-Json -Depth 100
    [pscustomobject]@{
        Policy = @{ Name = $PolicyName; Locations = $locations; EnforcementPlanes = @('CopilotExperiences'); Mode = $Mode }
        Rule   = @{ Name = "$PolicyName - rule"; Policy = $PolicyName; AdvancedRule = $advanced
                    RestrictAccess = @(@{ setting = 'ExcludeContentProcessing'; value = 'Block' }) }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    foreach ($c in 'Get-Label', 'New-DlpCompliancePolicy', 'New-DlpComplianceRule') {
        if (-not (Get-Command $c -ErrorAction SilentlyContinue)) { throw "$c not found. Run Connect-IPPSSession first (module ExchangeOnlineManagement)." }
    }
    $guids = @(Resolve-LabelGuids -Names $LabelName)
    $plan = New-CopilotDlpPlan -PolicyName $PolicyName -LabelGuids $guids -Mode $Mode
    if (-not $Apply) {
        Write-Host "Dry run (no -Apply). Would create:"
        $plan | ConvertTo-Json -Depth 8
        return
    }
    $pol = $plan.Policy; $rule = $plan.Rule
    New-DlpCompliancePolicy -Name $pol.Name -Locations $pol.Locations -EnforcementPlanes $pol.EnforcementPlanes -Mode $pol.Mode | Out-Null
    New-DlpComplianceRule -Name $rule.Name -Policy $rule.Policy -AdvancedRule $rule.AdvancedRule -RestrictAccess $rule.RestrictAccess | Out-Null
    Write-Host "Created '$($pol.Name)' in mode $($pol.Mode). Updates can take up to four hours to reach Copilot (Learn)."
}
