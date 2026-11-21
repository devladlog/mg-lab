#Requires -Version 7.2
<#
.SYNOPSIS
    Hybrid migration planning runner: pick the path, check Active Directory before directory sync, plan waves, fix UPN suffixes.
.DESCRIPTION
    Mode Strategy     pure decision from the Learn table. No connection needed.
    Mode Directory    read-only check of AD users (live Get-ADUser with -SearchBase, or -UsersFile json) against the verified domains of the tenant
                      (-VerifiedDomain, or -LiveDomains to read them with Microsoft Graph Get-MgDomain).
    Mode Waves        wave plan + one CSV per wave + the New-MigrationBatch commands (text only). Input: -MailboxesFile json, or -FromExchangeOnline (live, read-only).
    Mode FixUpn       changes the UPN suffix of accounts flagged UpnNonRoutable, only if directory.upnFix.allowedRules lists it; -SearchBase is mandatory; -WhatIf, rollback file.
    Mode RestoreUpn   puts the old UPNs back from the rollback file.
    Nothing here installs Microsoft Entra Connect or starts a synchronization.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidateSet('Strategy', 'Directory', 'Waves', 'FixUpn', 'RestoreUpn')][string]$Mode = 'Directory',
    [string]$ConfigFile = (Join-Path $PSScriptRoot 'migration.json'),
    # Strategy
    [ValidateSet('Exchange2003', 'Exchange2007', 'Exchange2010OrLater', 'ExchangeLegacy', 'NonExchange')][string]$Source,
    [int]$Mailboxes, [ValidateSet('AllAtOnce', 'Gradual')][string]$Pace = 'AllAtOnce', [switch]$ManageUsersOnPremises,
    # Directory / FixUpn
    [string]$SearchBase, [string]$Server, [string]$UsersFile, [string[]]$VerifiedDomain, [switch]$LiveDomains,
    # Waves
    [string]$MailboxesFile, [switch]$FromExchangeOnline, [string[]]$PilotUsers = @(), [string]$WaveDirectory = './waves',
    # shared
    [string]$OutFile, [string]$RollbackFile
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'HybridMigration/HybridMigration.psd1') -Force
$cfg = Get-HMConfig -Path $ConfigFile

function Get-Verified {
    if ($VerifiedDomain) { return $VerifiedDomain }
    if (-not $LiveDomains) { throw 'Give -VerifiedDomain <domain,...> or -LiveDomains.' }
    if (-not (Get-MgContext)) { Connect-MgGraph -Scopes 'Domain.Read.All' -NoWelcome }
    @(Get-MgDomain -All | Where-Object IsVerified | ForEach-Object Id)
}
function Get-Users {
    if ($UsersFile) { return @(Get-Content -LiteralPath $UsersFile -Raw | ConvertFrom-Json) }
    Get-HMDirectoryInventory -SearchBase $SearchBase -Server $Server
}
function Write-Report([string]$Text) { if ($OutFile) { Set-Content -LiteralPath $OutFile -Value $Text -Encoding utf8; Write-Host "Report written to $OutFile" } else { Write-Host $Text } }

switch ($Mode) {
    'Strategy' {
        if (-not $Source -or -not $Mailboxes) { throw 'Mode Strategy needs -Source and -Mailboxes.' }
        $s = Get-HMStrategy -Source $Source -Mailboxes $Mailboxes -Pace $Pace -ManageUsersOnPremises:$ManageUsersOnPremises
        Write-Report (ConvertTo-HMMarkdown -Strategy $s -Title 'Migration plan')
        $s
    }
    'Directory' {
        $users = Get-Users; $domains = Get-Verified
        $f = Get-HMDirectoryFinding -Users $users -VerifiedDomains $domains -Config $cfg
        Write-Report (ConvertTo-HMMarkdown -Findings $f)
        $f | Format-Table Severity, Rule, Account, Detail -AutoSize -Wrap
        $sum = Get-HMSummary -Findings $f
        Write-Host ("Users checked: {0}. Findings: {1} ({2} high). Ready for directory synchronization: {3}." -f @($users).Count, $sum.Total, $sum.High, $sum.ReadyForSync)
    }
    'Waves' {
        $inv = if ($MailboxesFile) { @(Get-Content -LiteralPath $MailboxesFile -Raw | ConvertFrom-Json) }
        elseif ($FromExchangeOnline) {
            if (-not (Get-ConnectionInformation -ErrorAction SilentlyContinue)) { Connect-ExchangeOnline -ShowBanner:$false }
            Get-HMMailboxInventory -PilotUsers $PilotUsers
        }
        else { throw 'Give -MailboxesFile or -FromExchangeOnline.' }
        $plan = New-HMWavePlan -Mailboxes $inv -Config $cfg
        Write-Report (ConvertTo-HMMarkdown -Plan $plan -Title 'Migration waves')
        $files = Export-HMWaveCsv -Plan $plan -Directory $WaveDirectory -Config $cfg
        foreach ($w in $plan.Waves) {
            Write-Host "`n# $($w.Name) ($($w.Kind), $($w.Count) mailboxes, $($w.TotalGB) GB). Not run: needs an on-premises Exchange endpoint."
            Write-Host (Get-HMBatchCommand -Wave $w -Config $cfg -CsvPath (Join-Path $WaveDirectory "$($w.Name).csv"))
        }
        $plan.Waves | Select-Object Name, Kind, Count, TotalGB, @{ n = 'Departments'; e = { $_.Departments -join ', ' } } | Format-Table -AutoSize
    }
    'FixUpn' {
        if (-not $SearchBase -and -not $UsersFile) { throw 'Mode FixUpn needs -SearchBase (never the whole domain by accident).' }
        if (-not $RollbackFile) { throw 'Mode FixUpn needs -RollbackFile.' }
        $users = Get-Users; $domains = Get-Verified
        $f = Get-HMDirectoryFinding -Users $users -VerifiedDomains $domains -Config $cfg
        $plan = Get-HMUpnFixPlan -Users $users -Findings $f -VerifiedDomains $domains -Config $cfg
        Write-Host "Fix plan: $(@($plan | Where-Object { -not $_.Skip }).Count) change(s), $(@($plan | Where-Object Skip).Count) skipped."
        $plan | Format-Table Account, OldUpn, NewUpn, Skip -AutoSize
        Invoke-HMUpnFix -Plan $plan -RollbackFile $RollbackFile -Server $Server -WhatIf:$WhatIfPreference 
    }
    'RestoreUpn' {
        if (-not $RollbackFile) { throw 'Mode RestoreUpn needs -RollbackFile.' }
        Restore-HMUpn -RollbackFile $RollbackFile -Server $Server -WhatIf:$WhatIfPreference
    }
}
