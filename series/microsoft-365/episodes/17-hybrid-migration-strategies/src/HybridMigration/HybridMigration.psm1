#Requires -Version 7.2
Set-StrictMode -Version Latest

# Limits below come from Microsoft Learn, "Prepare for directory synchronization to Microsoft 365" (attribute table) and
# "Decide on a migration path in Exchange Online". Everything that decides something is a pure function, so it is testable without a tenant.

$script:UpnBadChars = '[\\%&*+/=?{}|<>();:,\[\]"#\s]'
$script:ProxyBadChars = '[<>();,\[\]"\s\\]'     # Learn: proxyAddresses invalid characters < > ( ) ; , [ ] " and no space
$script:SamBadChars = '[\[\]\\"|,/:<>+=;?*'']'   # Learn: sAMAccountName invalid characters

function Get-HMConfig {
    [CmdletBinding()]
    param([string]$Path = (Join-Path $PSScriptRoot '..' 'migration.json'))
    $c = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -Depth 10
    foreach ($k in 'directory', 'waves', 'batch') { if (-not $c.PSObject.Properties[$k]) { throw "Config '$Path' has no '$k' section." } }
    foreach ($k in 'maxMailboxesPerWave', 'maxGBPerWave', 'largeMailboxGB') {
        if (-not $c.waves.PSObject.Properties[$k] -or [double]$c.waves.$k -le 0) { throw "Config: waves.$k must be a number greater than zero." }
    }
    $c
}

# ---------------------------------------------------------------- 1. Which migration path?

function Get-HMStrategy {
    <#
    .SYNOPSIS Pick the Exchange migration path from the table on Microsoft Learn (Decide on a migration path / decommission page).
    .DESCRIPTION Source: Exchange2003, Exchange2007, Exchange2010OrLater, ExchangeLegacy (2000 or earlier) or NonExchange (any IMAP server).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Exchange2003', 'Exchange2007', 'Exchange2010OrLater', 'ExchangeLegacy', 'NonExchange')][string]$Source,
        [Parameter(Mandatory)][ValidateRange(1, 1000000)][int]$Mailboxes,
        [ValidateSet('AllAtOnce', 'Gradual')][string]$Pace = 'AllAtOnce',
        [switch]$ManageUsersOnPremises
    )
    $reasons = [System.Collections.Generic.List[string]]::new()
    $warn = [System.Collections.Generic.List[string]]::new()
    $url = 'https://learn.microsoft.com/exchange/mailbox-migration/decide-on-a-migration-path'
    $small = $Mailboxes -lt 150
    $path = $null

    switch ($Source) {
        { $_ -in 'ExchangeLegacy', 'NonExchange' } {
            $path = 'IMAP'
            $reasons.Add('Exchange 2000 or earlier, and non-Exchange systems, can only be moved with an IMAP migration.')
            $warn.Add('IMAP migration copies only email: calendar items, contacts and tasks do not move, and the mailboxes must exist in Exchange Online first.')
        }
        'Exchange2010OrLater' {
            $warn.Add('A staged migration cannot move Exchange 2010 or later mailboxes.')
            if ($small -and $Pace -eq 'AllAtOnce' -and -not $ManageUsersOnPremises) {
                $path = 'Cutover'
                $reasons.Add("Under 150 mailboxes, all at once, and no need to keep managing users on-premises: cutover (or Express migration).")
            }
            else {
                $path = 'Hybrid'
                if (-not $small) { $reasons.Add("$Mailboxes mailboxes is 150 or more: cutover performance suffers, so move a limited number at a time with a hybrid deployment.") }
                if ($Pace -eq 'Gradual') { $reasons.Add('You want to move a few users at a time: hybrid remote moves.') }
                if ($ManageUsersOnPremises) { $reasons.Add('Users stay managed in on-premises Active Directory: that means directory synchronization, which a hybrid deployment has.') }
            }
        }
        { $_ -in 'Exchange2003', 'Exchange2007' } {
            if ($small -and $Pace -eq 'AllAtOnce' -and -not $ManageUsersOnPremises) {
                $path = 'Cutover'
                $reasons.Add('Under 150 mailboxes, all at once, users not managed on-premises: cutover.')
            }
            else {
                $path = 'Staged'
                if (-not $small) { $reasons.Add("$Mailboxes mailboxes is 150 or more: use staged migration, which moves a limited number of users at a time.") }
                if ($Pace -eq 'Gradual') { $reasons.Add('You want to move a few users at a time: staged.') }
                if ($ManageUsersOnPremises) { $reasons.Add('Users stay managed on-premises: staged (or a hybrid remote move).') }
            }
            $warn.Add('Exchange 2003 and 2007 are out of support (April 2014 and April 2017 per Learn).')
        }
    }

    if ($path -eq 'Cutover' -and $Mailboxes -ge 2000) { $path = 'Hybrid'; $reasons.Add('A cutover migration is limited to fewer than 2,000 mailboxes.') }
    if ($path -in 'Staged', 'Hybrid') { $warn.Add('Staged and hybrid migrations require directory synchronization first (run the directory check in this episode).') }
    if ($path -eq 'Staged') { $warn.Add('A staged migration CSV holds at most 2,000 rows; use one CSV per batch.') }
    if ($path -eq 'Cutover') { $warn.Add('The primary on-premises domain must be an accepted domain in Microsoft 365. Users are created in the cloud, and you still assign licences afterwards.') }
    if ($path -eq 'Hybrid' -and $Mailboxes -lt 2000) {
        $warn.Add('Learn: a hybrid deployment brings real complexity; with fewer than 2,000 mailboxes, check first whether a cutover (or staged, for Exchange 2003 and 2007) fits.')
    }
    [pscustomobject]@{
        Source = $Source; Mailboxes = $Mailboxes; Pace = $Pace; ManageUsersOnPremises = [bool]$ManageUsersOnPremises
        Strategy = $path; Reasons = @($reasons); Warnings = @($warn); Learn = $url
    }
}

# ---------------------------------------------------------------- 2. Is Active Directory ready for directory sync?

function Get-HMDirectoryInventory {
    <# Reads user objects from Active Directory (ActiveDirectory module). Read-only. #>
    [CmdletBinding()]
    param([string]$SearchBase, [string]$Server)
    $props = 'userPrincipalName', 'mail', 'proxyAddresses', 'mailNickname', 'displayName', 'givenName', 'sn', 'sAMAccountName', 'targetAddress', 'enabled'
    $p = @{ Filter = '*'; Properties = $props }
    if ($SearchBase) { $p.SearchBase = $SearchBase }
    if ($Server) { $p.Server = $Server }
    @(Get-ADUser @p | ForEach-Object {
            [pscustomobject]@{
                Dn = [string]$_.DistinguishedName; Sam = [string]$_.SamAccountName; Upn = [string]$_.UserPrincipalName
                Mail = [string]$_.mail; MailNickname = [string]$_.mailNickname; DisplayName = [string]$_.DisplayName
                GivenName = [string]$_.GivenName; Surname = [string]$_.Surname; TargetAddress = [string]$_.targetAddress
                ProxyAddresses = @($_.proxyAddresses | ForEach-Object { [string]$_ }); Enabled = [bool]$_.Enabled
            }
        })
}

function script:New-Finding([string]$Severity, [string]$Rule, $User, [string]$Detail, [bool]$Fixable = $false) {
    [pscustomobject]@{ Severity = $Severity; Rule = $Rule; Account = $User.Sam; Dn = $User.Dn; Detail = $Detail; Fixable = $Fixable }
}

function script:Test-UpnShape([string]$Upn) {
    # returns a list of problems for a userPrincipalName, per the Learn attribute table
    $p = [System.Collections.Generic.List[string]]::new()
    if ([string]::IsNullOrWhiteSpace($Upn)) { $p.Add('UpnMissing: empty'); return $p }
    $at = $Upn.IndexOf('@')
    if ($at -lt 0) { $p.Add('UpnFormat: no @ sign'); return $p }
    if ($at -eq 0) { $p.Add('UpnFormat: starts with @') }
    $local = $Upn.Substring(0, [Math]::Max($at, 0)); $domain = $Upn.Substring($at + 1)
    if ($Upn.Length -gt 113) { $p.Add("UpnTooLong: $($Upn.Length) characters (maximum 113)") }
    if ($local.Length -gt 64) { $p.Add("UpnTooLong: user name part is $($local.Length) characters (maximum 64)") }
    if ($domain.Length -gt 48) { $p.Add("UpnTooLong: domain part is $($domain.Length) characters (maximum 48)") }
    if ($local -match '[.&@ ]$') { $p.Add('UpnFormat: user name ends with a period, ampersand, space or at sign') }
    if ($Upn -match $script:UpnBadChars) { $p.Add("UpnInvalidChars: contains '$($Matches[0].Trim())' (or a space)") }
    elseif ($Upn -match '[^\u0000-\u007F]') { $p.Add('UpnInvalidChars: letters with diacritical marks or other non-ASCII characters') }
    $p
}

function Get-HMDirectoryFinding {
    <#
    .SYNOPSIS Check AD user objects against the directory-synchronization attribute rules on Microsoft Learn. Pure: no AD, no tenant.
    .PARAMETER VerifiedDomains Domains verified in the Microsoft 365 tenant. A UPN suffix outside this list is a finding.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Users,
        [Parameter(Mandatory)][string[]]$VerifiedDomains,
        $Config
    )
    $ignore = @(); if ($Config -and $Config.directory.ignoreAccounts) { $ignore = @($Config.directory.ignoreAccounts) }
    $verified = @($VerifiedDomains | ForEach-Object { $_.ToLowerInvariant() })
    $list = @($Users | Where-Object { $_.Sam -notin $ignore })
    $out = [System.Collections.Generic.List[object]]::new()

    foreach ($u in $list) {
        # --- userPrincipalName
        foreach ($problem in (Test-UpnShape $u.Upn)) {
            $rule, $detail = $problem -split ': ', 2
            $out.Add((New-Finding 'High' $rule $u "UPN '$($u.Upn)': $detail"))
        }
        if ($u.Upn -and $u.Upn.Contains('@') -and $u.Upn.IndexOf('@') -gt 0) {
            $suffix = $u.Upn.Substring($u.Upn.IndexOf('@') + 1).ToLowerInvariant()
            if ($suffix -notin $verified) {
                $out.Add((New-Finding 'High' 'UpnNonRoutable' $u "UPN suffix '$suffix' is not a verified domain in the tenant. Learn: such a UPN is synchronized to the onmicrosoft.com domain instead." $true))
            }
        }
        # --- proxyAddresses
        foreach ($pa in $u.ProxyAddresses) {
            $addr = if ($pa -match '^[^:]+:(.*)$') { $Matches[1] } else { $pa }
            if ($pa.Length -gt 256) { $out.Add((New-Finding 'High' 'ProxyTooLong' $u "proxyAddresses value is $($pa.Length) characters (maximum 256)")); continue }
            if ($addr -match $script:ProxyBadChars) { $out.Add((New-Finding 'High' 'ProxyInvalidChars' $u "proxyAddresses '$pa' has a space or one of < > ( ) ; , [ ] `" (Learn: a space makes the value be discarded and regenerated)")) }
            elseif ($addr -match '[^\u0000-\u007F]') { $out.Add((New-Finding 'High' 'ProxyInvalidChars' $u "proxyAddresses '$pa' has letters with diacritical marks")) }
        }
        # --- other attributes
        if ($u.Sam.Length -gt 20) { $out.Add((New-Finding 'Medium' 'SamTooLong' $u "sAMAccountName is $($u.Sam.Length) characters (maximum 20)")) }
        if ($u.Sam -match $script:SamBadChars) { $out.Add((New-Finding 'Medium' 'SamInvalidChars' $u "sAMAccountName contains '$($Matches[0])'")) }
        if ([string]::IsNullOrEmpty($u.DisplayName)) { $out.Add((New-Finding 'Low' 'DisplayNameMissing' $u 'displayName is empty (Learn: if the attribute exists it must have a value)')) }
        elseif ($u.DisplayName.Length -gt 256) { $out.Add((New-Finding 'Medium' 'DisplayNameTooLong' $u "displayName is $($u.DisplayName.Length) characters (maximum 256)")) }
        if ($u.GivenName.Length -gt 64) { $out.Add((New-Finding 'Low' 'GivenNameTooLong' $u "givenName is $($u.GivenName.Length) characters (maximum 64)")) }
        if ($u.MailNickname.StartsWith('.')) { $out.Add((New-Finding 'Medium' 'MailNicknameLeadingDot' $u "mailNickname '$($u.MailNickname)' starts with a period")) }
        if ($u.TargetAddress -and $u.TargetAddress -match '[<>();,\[\]"\s\\]') { $out.Add((New-Finding 'High' 'TargetAddressInvalid' $u "targetAddress '$($u.TargetAddress)' has a space or an invalid character")) }
        # alignment (Learn recommends UPN = primary SMTP address)
        $primary = @($u.ProxyAddresses | Where-Object { $_ -cmatch '^SMTP:' } | ForEach-Object { $_.Substring(5) })
        if ($primary.Count -eq 1 -and $u.Upn -and ($primary[0] -ne $u.Upn)) {
            $out.Add((New-Finding 'Low' 'UpnMailMismatch' $u "UPN '$($u.Upn)' differs from the primary SMTP address '$($primary[0])' (Learn recommends aligning them)"))
        }
        if ($primary.Count -gt 1) { $out.Add((New-Finding 'Medium' 'MultiplePrimarySmtp' $u "$($primary.Count) values start with SMTP: (one primary address expected)")) }
    }

    # --- duplicates (UPN, mail, proxyAddresses): the first object syncs, the others do not appear (Learn)
    $dup = {
        param($rule, $label, $selector)
        $pairs = foreach ($u in $list) { foreach ($v in @(& $selector $u)) { if ($v) { [pscustomobject]@{ User = $u; Value = $v.ToLowerInvariant() } } } }
        foreach ($g in ($pairs | Group-Object Value)) {
            $owners = @($g.Group.User | Sort-Object Sam -Unique)
            if ($owners.Count -lt 2) { continue }
            foreach ($o in $owners) {
                $others = ($owners | Where-Object Sam -NE $o.Sam | ForEach-Object Sam) -join ', '
                $out.Add((New-Finding 'High' $rule $o "$label '$($g.Name)' is also used by: $others"))
            }
        }
    }
    & $dup 'UpnDuplicate' 'UPN' { param($u) $u.Upn }
    & $dup 'MailDuplicate' 'mail' { param($u) $u.Mail }
    & $dup 'ProxyDuplicate' 'proxyAddress' { param($u) $u.ProxyAddresses | ForEach-Object { if ($_ -match '^[^:]+:(.*)$') { $Matches[1] } else { $_ } } }

    $order = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
    @($out | Sort-Object { $order[$_.Severity] }, Account, Rule)
}

function Get-HMSummary {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Findings)
    $by = @{}; foreach ($s in 'High', 'Medium', 'Low', 'Info') { $by[$s] = @($Findings | Where-Object Severity -EQ $s).Count }
    [pscustomobject]@{
        Total = $Findings.Count; High = $by.High; Medium = $by.Medium; Low = $by.Low; Info = $by.Info
        AccountsAffected = @($Findings | Select-Object -ExpandProperty Account -Unique).Count
        Fixable = @($Findings | Where-Object Fixable).Count
        ReadyForSync = ($by.High -eq 0)
    }
}

# ---------------------------------------------------------------- 3. Waves

function Get-HMMailboxInventory {
    <# Reads mailboxes from Exchange Online (needs Connect-ExchangeOnline): size, type, department; a shared mailbox is tied (MoveWith) to the first user with Full Access. Read-only.
       In the lab there is no on-premises Exchange, so this is the "inventory" input of the wave planner, taken from the cloud mailboxes. #>
    [CmdletBinding()]
    param([string[]]$PilotUsers = @())
    $users = @{}; foreach ($u in @(Get-User -ResultSize Unlimited)) { $users[[string]$u.UserPrincipalName] = $u }
    $boxes = @(Get-EXOMailbox -RecipientTypeDetails UserMailbox, SharedMailbox, RoomMailbox, EquipmentMailbox -ResultSize Unlimited -Properties PrimarySmtpAddress, RecipientTypeDetails, UserPrincipalName)
    $emailByUpn = @{}; foreach ($b in $boxes) { $emailByUpn[([string]$b.UserPrincipalName).ToLowerInvariant()] = [string]$b.PrimarySmtpAddress }
    foreach ($b in $boxes) {
        $st = Get-EXOMailboxStatistics -Identity $b.UserPrincipalName
        $bytes = if ("$($st.TotalItemSize)" -match '\(([\d,\.\s]+) bytes\)') { [double](($Matches[1] -replace '[^\d]', '')) } else { throw "Cannot read the size of $($b.UserPrincipalName): '$($st.TotalItemSize)'" }
        $type = ([string]$b.RecipientTypeDetails) -replace 'Mailbox$', ''
        $with = $null
        if ($type -eq 'Shared') {
            $fa = @(Get-EXOMailboxPermission -Identity $b.UserPrincipalName | Where-Object { $_.AccessRights -contains 'FullAccess' -and -not $_.IsInherited -and -not $_.Deny -and $_.User -notmatch '^NT AUTHORITY' } | Select-Object -First 1)
            if ($fa.Count -and $emailByUpn.ContainsKey(([string]$fa[0].User).ToLowerInvariant())) { $with = $emailByUpn[([string]$fa[0].User).ToLowerInvariant()] }
        }
        [pscustomobject]@{
            Email = [string]$b.PrimarySmtpAddress; SizeGB = [math]::Round($bytes / 1GB, 3); Type = $type
            Department = [string]$users[[string]$b.UserPrincipalName].Department; MoveWith = $with
            Pilot = ([string]$b.UserPrincipalName -in $PilotUsers) -or ([string]$b.PrimarySmtpAddress -in $PilotUsers)
        }
    }
}

function script:Get-Opt($Object, [string]$Name) { $p = $Object.PSObject.Properties[$Name]; if ($p) { $p.Value } else { $null } }

function New-HMWavePlan {
    <#
    .SYNOPSIS Split mailboxes into waves that respect size caps and never separate mailboxes that must move together.
    .DESCRIPTION Input objects: Email, SizeGB, Type (User, Shared, Room, Equipment), Department, MoveWith (email of a mailbox this one must move with), Pilot (bool).
        Order: pilot first, then departments alphabetically, then groups holding a mailbox at or above waves.largeMailboxGB in their own waves at the end.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object[]]$Mailboxes, [Parameter(Mandatory)]$Config)
    $w = $Config.waves
    $maxN = [int]$w.maxMailboxesPerWave; $maxGB = [double]$w.maxGBPerWave; $large = [double]$w.largeMailboxGB
    $byEmail = @{}
    foreach ($m in $Mailboxes) {
        $k = ([string]$m.Email).ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($k)) { throw 'A mailbox without an Email was found in the input.' }
        if ($byEmail.ContainsKey($k)) { throw "Duplicate mailbox in the input: $k" }
        $byEmail[$k] = $m
    }
    $warnings = [System.Collections.Generic.List[string]]::new()

    # union-find over MoveWith edges
    $parent = @{}; foreach ($k in $byEmail.Keys) { $parent[$k] = $k }
    $find = { param($x) while ($parent[$x] -ne $x) { $parent[$x] = $parent[$parent[$x]]; $x = $parent[$x] }; $x }
    foreach ($k in @($byEmail.Keys)) {
        $mw = Get-Opt $byEmail[$k] 'MoveWith'
        if ([string]::IsNullOrWhiteSpace($mw)) { continue }
        $t = $mw.ToLowerInvariant()
        if (-not $byEmail.ContainsKey($t)) { $warnings.Add("$k should move with $t, which is not in the input: ignored."); continue }
        $ra = & $find $k; $rb = & $find $t; if ($ra -ne $rb) { $parent[$ra] = $rb }
    }
    $groups = @{}
    foreach ($k in $byEmail.Keys) { $r = & $find $k; if (-not $groups.ContainsKey($r)) { $groups[$r] = [System.Collections.Generic.List[object]]::new() }; $groups[$r].Add($byEmail[$k]) }

    $units = foreach ($g in $groups.Values) {
        $members = @($g | Sort-Object Email)
        $dept = @($members | ForEach-Object { Get-Opt $_ 'Department' } | Where-Object { $_ }) | Select-Object -First 1
        $withUser = @($members | Where-Object { (Get-Opt $_ 'Type') -eq 'User' } | ForEach-Object { Get-Opt $_ 'Department' } | Where-Object { $_ }) | Select-Object -First 1
        if ($withUser) { $dept = $withUser }
        [pscustomobject]@{
            Members = $members; GB = [double](($members | Measure-Object SizeGB -Sum).Sum); Dept = [string]$dept
            Pilot = [bool](@($members | Where-Object { (Get-Opt $_ 'Pilot') -eq $true }).Count)
            Large = [bool](@($members | Where-Object { [double]$_.SizeGB -ge $large }).Count)
        }
    }
    $units = @($units)
    $pilot = @($units | Where-Object Pilot | Sort-Object Dept, { $_.Members[0].Email })
    $big = @($units | Where-Object { -not $_.Pilot -and $_.Large } | Sort-Object GB -Descending)
    $rest = @($units | Where-Object { -not $_.Pilot -and -not $_.Large } | Sort-Object Dept, @{ Expression = 'GB'; Descending = $true }, { $_.Members[0].Email })

    $waves = [System.Collections.Generic.List[object]]::new()
    $new = { param($kind) [pscustomobject]@{ Kind = $kind; Members = [System.Collections.Generic.List[object]]::new(); GB = 0.0; Notes = [System.Collections.Generic.List[string]]::new() } }
    $place = {
        param($list, $kind, [bool]$ownWave)
        $cur = $null
        foreach ($u in $list) {
            $oversize = ($u.Members.Count -gt $maxN) -or ($u.GB -gt $maxGB)
            if ($ownWave -or $oversize -or $null -eq $cur -or ($cur.Members.Count + $u.Members.Count -gt $maxN) -or ($cur.GB + $u.GB -gt $maxGB)) {
                $cur = & $new $kind; $waves.Add($cur)
            }
            foreach ($m in $u.Members) { $cur.Members.Add($m) }; $cur.GB += $u.GB
            if ($oversize) {
                $cur.Notes.Add("A group of $($u.Members.Count) mailboxes that must move together ($([math]::Round($u.GB, 1)) GB) is above the wave caps; it has a wave to itself.")
                $warnings.Add("Group around $($u.Members[0].Email) exceeds the wave caps ($maxN mailboxes / $maxGB GB).")
                $cur = $null
            }
            elseif ($ownWave) { $cur = $null }
        }
    }
    & $place $pilot 'Pilot' $false
    # a pilot is one wave only: everything that follows starts a fresh wave
    $pilotCount = $waves.Count
    & $place $rest 'Production' $false
    & $place $big 'Large' $true
    if ($pilotCount -gt 1) { $warnings.Add("The pilot needed $pilotCount waves; shrink the pilot or raise the caps.") }

    $n = 0
    $result = foreach ($wv in $waves) {
        $n++
        [pscustomobject]@{
            Wave = $n; Name = ('wave-{0:00}' -f $n); Kind = $wv.Kind
            Count = $wv.Members.Count; TotalGB = [math]::Round($wv.GB, 2)
            Departments = @($wv.Members | ForEach-Object { Get-Opt $_ 'Department' } | Where-Object { $_ } | Sort-Object -Unique)
            Mailboxes = @($wv.Members | Sort-Object Email); Notes = @($wv.Notes)
        }
    }
    [pscustomobject]@{ Waves = @($result); Warnings = @($warnings); TotalMailboxes = $byEmail.Count; TotalGB = [math]::Round(($Mailboxes | Measure-Object SizeGB -Sum).Sum, 2) }
}

function Export-HMWaveCsv {
    <# One CSV per wave with the columns the migration batch CSV accepts: EmailAddress, BadItemLimit, LargeItemLimit (Learn: "CSV files for mailbox migration"). #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][string]$Directory, [Parameter(Mandatory)]$Config)
    $bad = if ($Config.waves.PSObject.Properties['badItemLimit']) { $Config.waves.badItemLimit } else { 0 }
    $lg = if ($Config.waves.PSObject.Properties['largeItemLimit']) { $Config.waves.largeItemLimit } else { 0 }
    if (-not (Test-Path -LiteralPath $Directory)) { if ($PSCmdlet.ShouldProcess($Directory, 'Create folder')) { New-Item -ItemType Directory -Path $Directory | Out-Null } }
    foreach ($wv in $Plan.Waves) {
        $path = Join-Path $Directory "$($wv.Name).csv"
        if ($PSCmdlet.ShouldProcess($path, "Write $($wv.Count) rows")) {
            $wv.Mailboxes | ForEach-Object { [pscustomobject]@{ EmailAddress = $_.Email; BadItemLimit = $bad; LargeItemLimit = $lg } } | Export-Csv -LiteralPath $path -NoTypeInformation -Encoding utf8
            Get-Item -LiteralPath $path
        }
    }
}

function Get-HMBatchCommand {
    <# Returns the Exchange Online commands for one wave of an onboarding remote move (Learn: New-MigrationBatch example 3). Text only: nothing is run. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Wave, [Parameter(Mandatory)]$Config, [string]$CsvPath)
    if (-not $CsvPath) { $CsvPath = "./$($Wave.Name).csv" }
    $b = $Config.batch
    @(
        "New-MigrationBatch -Name '$($Wave.Name)' -SourceEndpoint '$($b.sourceEndpointName)' -TargetDeliveryDomain '$($b.targetDeliveryDomain)' -CSVData ([System.IO.File]::ReadAllBytes('$CsvPath'))"
        "Start-MigrationBatch -Identity '$($Wave.Name)'"
    ) -join [Environment]::NewLine
}

# ---------------------------------------------------------------- 4. Guarded fix: UPN suffix

function Get-HMUpnFixPlan {
    <# Pure. Builds the list of UPN changes (old suffix -> target suffix) the config allows. Never plans a change that makes a duplicate or an invalid UPN. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object[]]$Users, [Parameter(Mandatory)][object[]]$Findings, [Parameter(Mandatory)][string[]]$VerifiedDomains, [Parameter(Mandatory)]$Config)
    $fx = $Config.directory.upnFix
    if ('UpnNonRoutable' -notin @($fx.allowedRules)) { return @() }
    $target = ([string]$fx.targetSuffix).ToLowerInvariant()
    if (-not $target) { throw 'directory.upnFix.targetSuffix is empty.' }
    if ($target -notin @($VerifiedDomains | ForEach-Object { $_.ToLowerInvariant() })) { throw "directory.upnFix.targetSuffix '$target' is not a verified domain of the tenant." }
    $taken = @{}; foreach ($u in $Users) { if ($u.Upn) { $taken[$u.Upn.ToLowerInvariant()] = $true } }
    $plan = foreach ($f in ($Findings | Where-Object { $_.Rule -eq 'UpnNonRoutable' -and $_.Fixable })) {
        $u = $Users | Where-Object Dn -EQ $f.Dn | Select-Object -First 1
        $local = $u.Upn.Substring(0, $u.Upn.IndexOf('@'))
        $new = "$local@$target"
        $skip = $null
        if (Test-UpnShape $new) { $skip = "New UPN would be invalid: $((Test-UpnShape $new) -join '; ')" }
        elseif ($taken.ContainsKey($new.ToLowerInvariant())) { $skip = "New UPN '$new' is already used by another account." }
        else { $taken[$new.ToLowerInvariant()] = $true }
        [pscustomobject]@{ Dn = $u.Dn; Account = $u.Sam; OldUpn = $u.Upn; NewUpn = $new; Skip = $skip }
    }
    @($plan)
}

function Invoke-HMUpnFix {
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)][object[]]$Plan, [Parameter(Mandatory)][string]$RollbackFile, [string]$Server)
    if ((Test-Path -LiteralPath $RollbackFile) -and -not $WhatIfPreference) { throw "Rollback file '$RollbackFile' already exists: choose a new name (it is never overwritten)." }
    $done = [System.Collections.Generic.List[object]]::new()
    foreach ($p in $Plan) {
        if ($p.Skip) { [pscustomobject]@{ Account = $p.Account; Result = 'Skipped'; Detail = $p.Skip }; continue }
        $srv = @{}; if ($Server) { $srv.Server = $Server }
        $now = Get-ADUser -Identity $p.Dn -Properties userPrincipalName @srv
        if ([string]$now.UserPrincipalName -ne $p.OldUpn) { [pscustomobject]@{ Account = $p.Account; Result = 'Skipped'; Detail = "UPN changed since the audit ($($now.UserPrincipalName))." }; continue }
        if ($PSCmdlet.ShouldProcess($p.Dn, "Set UserPrincipalName $($p.OldUpn) -> $($p.NewUpn)")) {
            Set-ADUser -Identity $p.Dn -UserPrincipalName $p.NewUpn @srv -ErrorAction Stop
            $done.Add([pscustomobject]@{ Dn = $p.Dn; Account = $p.Account; OldUpn = $p.OldUpn; NewUpn = $p.NewUpn })
            $done | ConvertTo-Json -Depth 4 -AsArray | Set-Content -LiteralPath $RollbackFile -Encoding utf8
            [pscustomobject]@{ Account = $p.Account; Result = 'Changed'; Detail = "$($p.OldUpn) -> $($p.NewUpn)" }
        }
    }
}

function Restore-HMUpn {
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param([Parameter(Mandatory)][string]$RollbackFile, [string]$Server)
    $rows = @(Get-Content -LiteralPath $RollbackFile -Raw | ConvertFrom-Json)
    foreach ($r in $rows) {
        $srv = @{}; if ($Server) { $srv.Server = $Server }
        $now = Get-ADUser -Identity $r.Dn -Properties userPrincipalName @srv
        if ([string]$now.UserPrincipalName -ne $r.NewUpn) { [pscustomobject]@{ Account = $r.Account; Result = 'Skipped'; Detail = "Current UPN is $($now.UserPrincipalName), not the one this tool set." }; continue }
        if ($PSCmdlet.ShouldProcess($r.Dn, "Set UserPrincipalName $($r.NewUpn) -> $($r.OldUpn)")) {
            Set-ADUser -Identity $r.Dn -UserPrincipalName $r.OldUpn @srv -ErrorAction Stop
            [pscustomobject]@{ Account = $r.Account; Result = 'Restored'; Detail = "$($r.NewUpn) -> $($r.OldUpn)" }
        }
    }
}

# ---------------------------------------------------------------- Report

function ConvertTo-HMMarkdown {
    [CmdletBinding()]
    param($Strategy, [object[]]$Findings, $Plan, [string]$Title = 'Hybrid migration readiness')
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine("# $Title").AppendLine()
    if ($Strategy) {
        $null = $sb.AppendLine('## Migration path').AppendLine()
        $null = $sb.AppendLine("Source **$($Strategy.Source)**, $($Strategy.Mailboxes) mailboxes, pace $($Strategy.Pace), users managed on-premises: $($Strategy.ManageUsersOnPremises) -> **$($Strategy.Strategy)**.").AppendLine()
        foreach ($r in $Strategy.Reasons) { $null = $sb.AppendLine("- $r") }
        foreach ($w in $Strategy.Warnings) { $null = $sb.AppendLine("- Note: $w") }
        $null = $sb.AppendLine()
    }
    if ($null -ne $Findings) {
        $s = Get-HMSummary -Findings $Findings
        $null = $sb.AppendLine('## Directory check').AppendLine()
        $null = $sb.AppendLine("Findings: $($s.Total) ($($s.High) high, $($s.Medium) medium, $($s.Low) low) on $($s.AccountsAffected) account(s). Ready for directory synchronization: **$(if ($s.ReadyForSync) { 'yes' } else { 'no, fix the high findings first' })**.").AppendLine()
        if ($Findings.Count) {
            $null = $sb.AppendLine('| Severity | Rule | Account | What was found |').AppendLine('|---|---|---|---|')
            foreach ($f in $Findings) { $null = $sb.AppendLine("| $($f.Severity) | $($f.Rule) | $($f.Account) | $(($f.Detail -replace '\|', '/')) |") }
            $null = $sb.AppendLine()
        }
    }
    if ($Plan) {
        $null = $sb.AppendLine('## Waves').AppendLine()
        $null = $sb.AppendLine("$($Plan.TotalMailboxes) mailboxes, $($Plan.TotalGB) GB, $($Plan.Waves.Count) wave(s).").AppendLine()
        $null = $sb.AppendLine('| Wave | Kind | Mailboxes | GB | Departments |').AppendLine('|---|---|---|---|---|')
        foreach ($w in $Plan.Waves) { $null = $sb.AppendLine("| $($w.Name) | $($w.Kind) | $($w.Count) | $($w.TotalGB) | $($w.Departments -join ', ') |") }
        $null = $sb.AppendLine()
        foreach ($w in $Plan.Warnings) { $null = $sb.AppendLine("- Warning: $w") }
    }
    $sb.ToString()
}

Export-ModuleMember -Function Get-HMMailboxInventory, Get-HMConfig, Get-HMStrategy, Get-HMDirectoryInventory, Get-HMDirectoryFinding, Get-HMSummary, New-HMWavePlan, Export-HMWaveCsv, Get-HMBatchCommand, ConvertTo-HMMarkdown, Get-HMUpnFixPlan, Invoke-HMUpnFix, Restore-HMUpn
