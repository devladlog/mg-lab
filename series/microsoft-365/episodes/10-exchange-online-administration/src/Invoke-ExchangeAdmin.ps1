#Requires -Version 7.2
<#
.SYNOPSIS
    Exchange Online administration runner: audit, guarded fix, shared mailboxes from a file, message trace.
.DESCRIPTION
    Mode Audit (default)            read-only: inventory + findings + markdown report. With -Snapshot it analyses a saved inventory offline.
    Mode Fix                        removes mailbox-level external forwarding for the rules listed in fix.allowedRules (empty by default), with -WhatIf and a rollback file.
    Mode Restore                    puts back what a rollback file recorded.
    Mode SyncSharedMailboxes        makes the shared mailboxes in -DesiredFile exist with the listed Full Access / Send As delegates (adds only; -RemoveExtra also removes).
    Mode Trace                      message trace (Get-MessageTraceV2) with the 10-day and 90-day limits checked.
    Everything except -Snapshot needs a Connect-ExchangeOnline session; the runner connects interactively if there is none.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet('Audit', 'Fix', 'Restore', 'SyncSharedMailboxes', 'Trace')][string]$Mode = 'Audit',
    [string]$ConfigFile = (Join-Path $PSScriptRoot 'exchange.json'),
    [string]$Snapshot,
    [string]$SaveSnapshot,
    [string]$OutFile,
    [string]$RollbackFile,
    [string]$DesiredFile = (Join-Path $PSScriptRoot 'shared-mailboxes.json'),
    [switch]$RemoveExtra,
    [switch]$SkipInboxRules,
    [string]$UserPrincipalName,
    [string]$SenderAddress, [string]$RecipientAddress, [string]$Subject, [string[]]$Status, [int]$Hours = 0
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'ExchangeAdmin/ExchangeAdmin.psd1') -Force

function Connect-EAExchange {
    param([string]$Upn)
    if (-not (Get-Command Get-EXOMailbox -ErrorAction SilentlyContinue)) { Import-Module ExchangeOnlineManagement -ErrorAction Stop }
    $connected = $null
    try { $connected = @(Get-ConnectionInformation -ErrorAction Stop | Where-Object { $_.State -eq 'Connected' }) } catch { $connected = @() }
    if ($connected.Count -eq 0) {
        $p = @{ ShowBanner = $false }
        if ($Upn) { $p.UserPrincipalName = $Upn }
        Connect-ExchangeOnline @p
    }
}

function Show-Table {
    param([object[]]$Rows)
    if (@($Rows).Count -eq 0) { return }
    ($Rows | Format-Table -AutoSize -Wrap | Out-String -Width 220).TrimEnd()
}

$config = Get-EAConfig -Path $ConfigFile

if ($Snapshot -and $Mode -ne 'Audit') { throw "-Snapshot is offline data: Mode $Mode needs the live tenant." }

switch ($Mode) {
    'Audit' {
        if ($Snapshot) { $inv = Get-Content -LiteralPath $Snapshot -Raw | ConvertFrom-Json }
        else {
            Connect-EAExchange -Upn $UserPrincipalName
            $inv = Get-EAInventory -SkipInboxRules:$SkipInboxRules
        }
        if ($SaveSnapshot) { $inv | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SaveSnapshot -Encoding utf8; "Snapshot saved: $SaveSnapshot (tenant data, do not commit)" }
        $findings = @(Get-EAFinding -Inventory $inv -Config $config)
        $plan = @(Get-EAFixPlan -Findings $findings -Config $config -Inventory $inv)
        $s = Get-EASummary -Findings $findings
        Show-Table ($findings | Select-Object Severity, Rule, Target, Detail)
        "Findings: $($s.Total) ($($s.High) high, $($s.Medium) medium, $($s.Low) low, $($s.Info) info). Fixable here: $($s.Fixable). Fix plan: $($plan.Count) removal(s)."
        if ($OutFile) { ConvertTo-EAMarkdown -Inventory $inv -Findings $findings -FixPlan $plan | Set-Content -LiteralPath $OutFile -Encoding utf8; "Report written: $OutFile" }
    }
    'Fix' {
        if (-not $RollbackFile) { throw 'Mode Fix needs -RollbackFile (where the removed forwarding is recorded).' }
        Connect-EAExchange -Upn $UserPrincipalName
        $inv = Get-EAInventory -SkipInboxRules
        $findings = @(Get-EAFinding -Inventory $inv -Config $config)
        $plan = @(Get-EAFixPlan -Findings $findings -Config $config -Inventory $inv)
        if ($plan.Count -eq 0) { 'Nothing to fix: fix.allowedRules is empty, or no allowed finding exists.'; return }
        Show-Table (Invoke-EAForwardingFix -Plan $plan -RollbackFile $RollbackFile)
    }
    'Restore' {
        if (-not $RollbackFile) { throw 'Mode Restore needs -RollbackFile.' }
        Connect-EAExchange -Upn $UserPrincipalName
        Show-Table (Restore-EAForwarding -RollbackFile $RollbackFile)
    }
    'SyncSharedMailboxes' {
        $desired = Get-Content -LiteralPath $DesiredFile -Raw | ConvertFrom-Json
        Connect-EAExchange -Upn $UserPrincipalName
        $inv = Get-EAInventory -SkipInboxRules
        $remove = $RemoveExtra -or [bool]($desired.PSObject.Properties['removeExtra'] -and $desired.removeExtra)
        $plan = @(Get-EASharedMailboxPlan -Desired $desired -Inventory $inv -RemoveExtra:$remove)
        if ($plan.Count -eq 0) { 'Already as declared: nothing to do.'; return }
        Show-Table (Invoke-EASharedMailboxPlan -Plan $plan -Desired $desired -RetryCount $config.provision.retryCount -RetrySeconds $config.provision.retrySeconds)
    }
    'Trace' {
        Connect-EAExchange -Upn $UserPrincipalName
        $p = @{ Config = $config; Hours = $Hours }
        foreach ($k in 'SenderAddress', 'RecipientAddress', 'Subject', 'Status') { if ($PSBoundParameters.ContainsKey($k)) { $p[$k] = Get-Variable $k -ValueOnly } }
        $rows = @(Get-EAMessageTrace @p)
        if ($rows.Count -eq 0) { 'No messages in that window. A message can take a few minutes to show up.' } else { Show-Table $rows }
    }
}
