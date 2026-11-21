#Requires -Version 7.2
<#
  DEVLADLOG Windows Server #2 - AdLab
  Build an OU structure and users from a CSV (idempotent), then export a snapshot of the domain and check its hygiene.

    * Pure functions (naming, plans, FILETIME conversion, Test-AdLabHygiene) run anywhere and carry the unit tests.
    * Invoke-AdLabProvisioning and Export-AdLabSnapshot call the ActiveDirectory module (RSAT / a domain controller).
      The tests mock those cmdlets; the real run happens in the lab (see demo.md).
#>

$script:SeverityOrder = @{ High = 0; Medium = 1; Low = 2; Info = 3 }

# Groups protected by AdminSDHolder (Learn: "Appendix C: Protected Accounts and Groups in Active Directory"),
# by SID so the export also works on non-English domain controllers. "D-" = domain SID + RID.
$script:ProtectedGroupSids = [ordered]@{
    'Administrators'        = 'S-1-5-32-544'
    'Account Operators'     = 'S-1-5-32-548'
    'Server Operators'      = 'S-1-5-32-549'
    'Print Operators'       = 'S-1-5-32-550'
    'Backup Operators'      = 'S-1-5-32-551'
    'Replicator'            = 'S-1-5-32-552'
    'Domain Admins'         = 'D-512'
    'Domain Controllers'    = 'D-516'
    'Schema Admins'         = 'D-518'
    'Enterprise Admins'     = 'D-519'
    'Read-only Domain Controllers' = 'D-521'
    'Key Admins'            = 'D-526'
    'Enterprise Key Admins' = 'D-527'
}
# The groups we expect to be (almost) empty day to day (Learn: Appendices E, F, G).
$script:TierZeroGroups = 'Enterprise Admins', 'Domain Admins', 'Administrators', 'Schema Admins'

# ---------------------------------------------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------------------------------------------
function ConvertTo-AdLabAscii {
    <# "João Gonçalves" -> "Joao Goncalves": decompose, drop the combining marks. #>
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)][AllowEmptyString()][string] $Text)
    $sb = [Text.StringBuilder]::new()
    foreach ($ch in $Text.Normalize([Text.NormalizationForm]::FormD).ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch) -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$sb.Append($ch)
        }
    }
    $sb.ToString().Normalize([Text.NormalizationForm]::FormC)
}

function ConvertTo-AdLabSamAccountName {
    <#
      first initial + surname, lowercase ASCII letters and digits only, at most 20 characters
      (sAMAccountName must be 20 characters or fewer). Multi-part surnames use the last part: "Ana Maria Silva Costa" -> acosta.
    #>
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)][string] $GivenName, [Parameter(Mandatory)][string] $Surname)
    $first = (ConvertTo-AdLabAscii $GivenName).ToLowerInvariant() -replace '[^a-z0-9]', ''
    $last = ((ConvertTo-AdLabAscii $Surname).Trim() -split '\s+')[-1].ToLowerInvariant() -replace '[^a-z0-9]', ''
    if (-not $first -or -not $last) { throw "Cannot build a logon name from '$GivenName' '$Surname'." }
    $sam = $first.Substring(0, 1) + $last
    if ($sam.Length -gt 20) { $sam = $sam.Substring(0, 20) }
    $sam
}

function Get-AdLabUniqueSamAccountName {
    <# Appends 2, 3, ... on collisions and still keeps the result within 20 characters. #>
    [CmdletBinding()] [OutputType([string])]
    param([Parameter(Mandatory)][string] $Base, [Parameter(Mandatory)][AllowEmptyCollection()][Collections.Generic.HashSet[string]] $Taken)
    if (-not $Taken.Contains($Base)) { return $Base }
    for ($i = 2; $i -lt 1000; $i++) {
        $suffix = "$i"
        $stem = if ($Base.Length + $suffix.Length -gt 20) { $Base.Substring(0, 20 - $suffix.Length) } else { $Base }
        $candidate = "$stem$suffix"
        if (-not $Taken.Contains($candidate)) { return $candidate }
    }
    throw "No free logon name for '$Base'."
}

function Get-AdLabOuPlan {
    <# Every OU we need, parents before children: OU=Contoso, then Users/Groups/Servers, then one OU per department. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $DomainDn,
        [string] $RootOu = 'Contoso',
        [Parameter(Mandatory)][string[]] $Department
    )
    $root = "OU=$RootOu,$DomainDn"
    [pscustomobject]@{ Name = $RootOu; Path = $DomainDn; DistinguishedName = $root }
    foreach ($n in 'Users', 'Groups', 'Servers') {
        [pscustomobject]@{ Name = $n; Path = $root; DistinguishedName = "OU=$n,$root" }
    }
    foreach ($d in ($Department | Sort-Object -Unique)) {
        [pscustomobject]@{ Name = $d; Path = "OU=Users,$root"; DistinguishedName = "OU=$d,OU=Users,$root" }
    }
}

function New-AdLabUserPlan {
    <#
      Turns CSV rows (EmployeeId, GivenName, Surname, Department, Title) into a plan.
      Matching on EmployeeId makes re-runs idempotent: existing people keep their logon name, new people get a unique one.
      -Existing: objects with EmployeeId and SamAccountName (what Get-ADUser returns in the lab).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object[]] $User,
        [Parameter(Mandatory)][string] $DomainDn,
        [Parameter(Mandatory)][string] $UpnSuffix,
        [string] $RootOu = 'Contoso',
        [AllowEmptyCollection()][object[]] $Existing = @()
    )
    $byEmployee = @{}
    $taken = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($e in $Existing) {
        if ($e.EmployeeId) { $byEmployee[[string]$e.EmployeeId] = $e }
        if ($e.SamAccountName) { [void]$taken.Add($e.SamAccountName) }
    }
    $seen = [Collections.Generic.HashSet[string]]::new()
    foreach ($u in $User) {
        $id = ([string]$u.EmployeeId).Trim()
        if (-not $id) { throw "Row for '$($u.GivenName) $($u.Surname)' has no EmployeeId." }
        if (-not $seen.Add($id)) { throw "EmployeeId '$id' appears twice in the input." }
        $given = ([string]$u.GivenName).Trim()
        $sur = ([string]$u.Surname).Trim()
        $dept = ([string]$u.Department).Trim()
        if ($byEmployee.ContainsKey($id)) {
            $sam = $byEmployee[$id].SamAccountName
            $action = 'Exists'
        }
        else {
            $sam = Get-AdLabUniqueSamAccountName -Base (ConvertTo-AdLabSamAccountName $given $sur) -Taken $taken
            [void]$taken.Add($sam)
            $action = 'Create'
        }
        [pscustomobject]@{
            Action         = $action
            EmployeeId     = $id
            GivenName      = $given
            Surname        = $sur
            DisplayName    = "$given $sur"
            SamAccountName = $sam
            UserPrincipalName = "$sam@$UpnSuffix"
            Department     = $dept
            Title          = ([string]$u.Title).Trim()
            Path           = "OU=$dept,OU=Users,OU=$RootOu,$DomainDn"
            Group          = "GG-Dept-$dept"
        }
    }
}

function ConvertFrom-AdLabFileTime {
    <#
      lastLogonTimestamp / pwdLastSet are FILETIMEs (100 ns since 1601-01-01 UTC).
      0 means "never"; Int64.MaxValue means "never" for accountExpires. Both come back as $null.
    #>
    [CmdletBinding()]
    param([AllowNull()] $FileTime)
    if ($null -eq $FileTime) { return $null }
    $v = [long]$FileTime
    if ($v -le 0 -or $v -eq [long]::MaxValue) { return $null }
    [datetime]::FromFileTimeUtc($v)
}

function ConvertTo-AdLabIso {
    param([AllowNull()] $Date)
    if ($null -eq $Date) { return $null }
    ([datetime]$Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
}

function ConvertFrom-AdLabIso {
    param([AllowNull()] $Text)
    if (-not $Text) { return $null }
    if ($Text -is [datetime]) { return $Text.ToUniversalTime() }
    [datetime]::Parse($Text, [cultureinfo]::InvariantCulture, 'AdjustToUniversal,AssumeUniversal')
}

function New-AdLabFinding {
    param([ValidateSet('High', 'Medium', 'Low', 'Info')][string] $Severity, [string] $Check, [string] $Object, [string] $Detail)
    [pscustomobject]@{ Severity = $Severity; Check = $Check; Object = $Object; Detail = $Detail }
}

function Test-AdLabHygiene {
    <#
      Checks an exported snapshot against a policy and returns findings (Severity, Check, Object, Detail).
      lastLogonTimestamp only replicates when it is 9 to 14 days old, so StaleDays is a threshold, not a stopwatch.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Snapshot,
        [Parameter(Mandatory)] $Policy,
        [datetime] $Now = [datetime]::UtcNow
    )
    $s = $Snapshot
    $p = $Policy
    $now = $Now.ToUniversalTime()
    $out = [Collections.Generic.List[object]]::new()

    # Who is in a protected (AdminSDHolder) group, directly or nested?
    $protectedMembers = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $tierZeroMembers = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($g in @($s.ProtectedGroups)) {
        foreach ($m in @($g.Members)) {
            [void]$protectedMembers.Add($m)
            if ($g.Name -in $script:TierZeroGroups) { [void]$tierZeroMembers.Add($m) }
        }
    }
    $builtinAdmin = $s.Domain.BuiltinAdministrator
    $staleCut = $now.AddDays(-$p.StaleDays)

    foreach ($u in @($s.Users)) {
        $sam = $u.SamAccountName
        if ($sam -eq 'krbtgt') { continue }                   # checked separately below
        $last = ConvertFrom-AdLabIso $u.LastLogonTimestamp
        $created = ConvertFrom-AdLabIso $u.WhenCreated
        $isTierZero = $tierZeroMembers.Contains($sam)

        if ($u.Enabled) {
            if ($null -eq $last -and $null -ne $created -and $created -lt $staleCut) {
                $out.Add((New-AdLabFinding Low 'NeverUsed' $sam "Enabled, created $($created.ToString('yyyy-MM-dd')), never signed in."))
            }
            elseif ($null -ne $last -and $last -lt $staleCut) {
                $days = [math]::Floor(($now - $last).TotalDays)
                $sev = if ($isTierZero) { 'High' } else { 'Medium' }
                $what = if ($isTierZero) { 'Privileged account' } else { 'Enabled account' }
                $out.Add((New-AdLabFinding $sev 'StaleUser' $sam "$what, last sign-in about $days days ago (lastLogonTimestamp can lag by up to 14 days)."))
            }
            if ($u.PasswordNeverExpires -and -not $u.HasSpn) {
                $sev = if ($isTierZero) { 'High' } else { 'Medium' }
                $out.Add((New-AdLabFinding $sev 'PasswordNeverExpires' $sam 'Password never expires on a user account.'))
            }
            if ($u.PasswordNeverExpires -and $u.HasSpn) {
                $out.Add((New-AdLabFinding Medium 'ServiceAccount' $sam 'User account with an SPN and a password that never expires. Consider a group Managed Service Account (gMSA).'))
            }
            if ($u.PasswordNotRequired) {
                $out.Add((New-AdLabFinding High 'PasswordNotRequired' $sam 'PASSWD_NOTREQD is set: this account may have an empty password.'))
            }
        }
        if ($u.AdminCount -eq 1 -and -not $protectedMembers.Contains($sam) -and $sam -ne $builtinAdmin) {
            $out.Add((New-AdLabFinding Low 'OrphanedAdminCount' $sam 'adminCount=1 but no longer in a protected group: inheritance stays off until you clear it.'))
        }
    }

    if ($s.Domain.GuestEnabled) {
        $out.Add((New-AdLabFinding High 'GuestEnabled' 'Guest' 'The built-in Guest account is enabled.'))
    }

    # Tier 0 group sizes: Learn says EA/DA/BA should hold no day-to-day users (except a secured built-in Administrator).
    foreach ($g in @($s.ProtectedGroups | Where-Object { $_.Name -in $script:TierZeroGroups })) {
        $people = @($g.Members | Where-Object { $_ -ne $builtinAdmin })
        if ($people.Count -gt $p.MaxTierZeroMembers) {
            $out.Add((New-AdLabFinding Medium 'PrivilegedGroup' $g.Name "$($people.Count) members besides the built-in Administrator: $($people -join ', '). Policy: at most $($p.MaxTierZeroMembers)."))
        }
    }

    foreach ($c in @($s.Computers)) {
        if (-not $c.Enabled) { continue }
        $last = ConvertFrom-AdLabIso $c.LastLogonTimestamp
        if ($null -ne $last -and $last -lt $staleCut) {
            $days = [math]::Floor(($now - $last).TotalDays)
            $out.Add((New-AdLabFinding Medium 'StaleComputer' $c.Name "Computer account last authenticated about $days days ago."))
        }
    }

    # Domain-wide settings
    $krbtgt = ConvertFrom-AdLabIso $s.Domain.KrbtgtPasswordLastSet
    if ($krbtgt) {
        $age = [math]::Floor(($now - $krbtgt).TotalDays)
        if ($age -gt $p.KrbtgtMaxAgeDays) {
            $out.Add((New-AdLabFinding Medium 'KrbtgtPassword' 'krbtgt' "krbtgt password is $age days old (policy: $($p.KrbtgtMaxAgeDays)). Reset it twice, at least 10 hours apart."))
        }
    }
    if (-not $s.Domain.RecycleBinEnabled) {
        $out.Add((New-AdLabFinding Medium 'RecycleBin' $s.Domain.DnsRoot 'Active Directory Recycle Bin is not enabled. Enabling it is irreversible, and only objects deleted afterwards can be restored from it.'))
    }
    if ($s.Domain.MinPasswordLength -lt $p.MinPasswordLength) {
        $out.Add((New-AdLabFinding Medium 'PasswordPolicy' $s.Domain.DnsRoot "Default domain policy minimum password length is $($s.Domain.MinPasswordLength) (policy: $($p.MinPasswordLength))."))
    }
    if ($s.Domain.LockoutThreshold -eq 0) {
        $out.Add((New-AdLabFinding Low 'LockoutPolicy' $s.Domain.DnsRoot 'Account lockout threshold is 0 (never locks out).'))
    }
    foreach ($lvl in @(@{ K = 'DomainMode'; V = $s.Domain.DomainMode }, @{ K = 'ForestMode'; V = $s.Domain.ForestMode })) {
        if ($p.TargetFunctionalLevel -and $lvl.V -notlike "*$($p.TargetFunctionalLevel)*") {
            $out.Add((New-AdLabFinding Info 'FunctionalLevel' $s.Domain.DnsRoot "$($lvl.K) is $($lvl.V) (target: $($p.TargetFunctionalLevel))."))
        }
    }

    $out | Sort-Object -Property @{ Expression = { $script:SeverityOrder[$_.Severity] } }, Check, Object
}

function ConvertTo-AdLabMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyCollection()][object[]] $Finding, [Parameter(Mandatory)][string] $Domain, [datetime] $Now = [datetime]::UtcNow)
    $sb = [Text.StringBuilder]::new()
    [void]$sb.AppendLine("# AD hygiene report: $Domain")
    [void]$sb.AppendLine('')
    $counts = foreach ($sev in 'High', 'Medium', 'Low', 'Info') { "$sev $(@($Finding | Where-Object Severity -eq $sev).Count)" }
    [void]$sb.AppendLine("Generated $($Now.ToUniversalTime().ToString('yyyy-MM-dd HH:mm')) UTC. $($counts -join ' / ').")
    [void]$sb.AppendLine('')
    [void]$sb.AppendLine('| Severity | Check | Object | Detail |')
    [void]$sb.AppendLine('|---|---|---|---|')
    foreach ($f in $Finding) { [void]$sb.AppendLine("| $($f.Severity) | $($f.Check) | $($f.Object) | $($f.Detail -replace '\|', '\|') |") }
    $sb.ToString()
}

# ---------------------------------------------------------------------------------------------------------------
# Lab functions (ActiveDirectory module required; mocked in the tests)
# ---------------------------------------------------------------------------------------------------------------
function Assert-AdLabModule {
    if (-not (Get-Command -Name Get-ADDomain -ErrorAction SilentlyContinue)) {
        Import-Module ActiveDirectory -ErrorAction Stop   # RSAT-AD-PowerShell, present on every DC
    }
}

function Invoke-AdLabProvisioning {
    <#
      Creates the OUs, one global security group per department and the users from the CSV. Safe to re-run:
      everything is looked up first and only missing objects are created. Supports -WhatIf.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string] $CsvPath,
        [Parameter(Mandatory)][string] $DomainDn,
        [Parameter(Mandatory)][string] $UpnSuffix,
        [Parameter(Mandatory)][securestring] $InitialPassword,
        [string] $RootOu = 'Contoso',
        [string] $Server
    )
    Assert-AdLabModule
    $ad = @{}
    if ($Server) { $ad.Server = $Server }
    $rows = @(Import-Csv -Path $CsvPath)
    $log = [Collections.Generic.List[object]]::new()

    # 1. OUs (parents first), protected from accidental deletion
    foreach ($ou in Get-AdLabOuPlan -DomainDn $DomainDn -RootOu $RootOu -Department $rows.Department) {
        $exists = Get-ADOrganizationalUnit @ad -Filter "DistinguishedName -eq '$($ou.DistinguishedName)'"
        if ($exists) { $log.Add([pscustomobject]@{ Action = 'Exists'; Type = 'OU'; Name = $ou.DistinguishedName }); continue }
        if ($PSCmdlet.ShouldProcess($ou.DistinguishedName, 'Create OU')) {
            New-ADOrganizationalUnit @ad -Name $ou.Name -Path $ou.Path -ProtectedFromAccidentalDeletion $true
            $log.Add([pscustomobject]@{ Action = 'Created'; Type = 'OU'; Name = $ou.DistinguishedName })
        }
    }

    # 2. Department groups in OU=Groups
    $groupPath = "OU=Groups,OU=$RootOu,$DomainDn"
    foreach ($dept in ($rows.Department | Sort-Object -Unique)) {
        $g = "GG-Dept-$dept"
        if (Get-ADGroup @ad -Filter "SamAccountName -eq '$g'") { $log.Add([pscustomobject]@{ Action = 'Exists'; Type = 'Group'; Name = $g }); continue }
        if ($PSCmdlet.ShouldProcess($g, 'Create group')) {
            New-ADGroup @ad -Name $g -SamAccountName $g -GroupScope Global -GroupCategory Security -Path $groupPath -Description "All users in $dept"
            $log.Add([pscustomobject]@{ Action = 'Created'; Type = 'Group'; Name = $g })
        }
    }

    # 3. Users: match on EmployeeID so a rename never creates a duplicate
    $existing = @(Get-ADUser @ad -Filter 'EmployeeID -like "*"' -Properties EmployeeID |
        ForEach-Object { [pscustomobject]@{ EmployeeId = $_.EmployeeID; SamAccountName = $_.SamAccountName } })
    # Every logon name already in the domain counts as taken, not only the CSV people.
    $allSam = @(Get-ADUser @ad -Filter * | ForEach-Object { [pscustomobject]@{ EmployeeId = $null; SamAccountName = $_.SamAccountName } })
    $plan = New-AdLabUserPlan -User $rows -DomainDn $DomainDn -UpnSuffix $UpnSuffix -RootOu $RootOu -Existing ($existing + $allSam)

    foreach ($u in $plan) {
        if ($u.Action -eq 'Exists') { $log.Add([pscustomobject]@{ Action = 'Exists'; Type = 'User'; Name = $u.SamAccountName }); continue }
        if ($PSCmdlet.ShouldProcess("$($u.SamAccountName) in $($u.Path)", 'Create user')) {
            $params = @{
                Name                  = $u.DisplayName
                GivenName             = $u.GivenName
                Surname               = $u.Surname
                DisplayName           = $u.DisplayName
                SamAccountName        = $u.SamAccountName
                UserPrincipalName     = $u.UserPrincipalName
                EmployeeID            = $u.EmployeeId
                Department            = $u.Department
                Title                 = $u.Title
                Path                  = $u.Path
                AccountPassword       = $InitialPassword
                ChangePasswordAtLogon = $true
                Enabled               = $true
            }
            New-ADUser @ad @params
            Add-ADGroupMember @ad -Identity $u.Group -Members $u.SamAccountName
            $log.Add([pscustomobject]@{ Action = 'Created'; Type = 'User'; Name = $u.SamAccountName })
        }
    }
    $log.ToArray()
}

function Export-AdLabSnapshot {
    <# Reads what Test-AdLabHygiene needs and returns it as one object (write it with ConvertTo-Json -Depth 6). #>
    [CmdletBinding()]
    param([string] $Server)
    Assert-AdLabModule
    $ad = @{}
    if ($Server) { $ad.Server = $Server }

    $domain = Get-ADDomain @ad
    $forest = Get-ADForest @ad
    $domainSid = $domain.DomainSID.Value
    $policy = Get-ADDefaultDomainPasswordPolicy @ad
    $recycle = Get-ADOptionalFeature @ad -Filter "Name -eq 'Recycle Bin Feature'"
    $krbtgt = Get-ADUser @ad -Identity "$domainSid-502" -Properties pwdLastSet
    $guest = Get-ADUser @ad -Identity "$domainSid-501"
    $admin = Get-ADUser @ad -Identity "$domainSid-500"

    $groups = foreach ($name in $script:ProtectedGroupSids.Keys) {
        $sid = $script:ProtectedGroupSids[$name] -replace '^D-', "$domainSid-"
        # Schema Admins and Enterprise Admins only exist in the forest root domain.
        $grp = Get-ADGroup @ad -Filter "SID -eq '$sid'"
        if (-not $grp) { continue }
        [pscustomobject]@{
            Name    = $name
            Members = @(Get-ADGroupMember @ad -Identity $grp -Recursive | Where-Object objectClass -eq 'user' | ForEach-Object SamAccountName)
        }
    }

    $users = Get-ADUser @ad -Filter * -Properties lastLogonTimestamp, whenCreated, PasswordNeverExpires, PasswordNotRequired, adminCount, servicePrincipalName |
        ForEach-Object {
            [pscustomobject]@{
                SamAccountName       = $_.SamAccountName
                Enabled              = [bool]$_.Enabled
                LastLogonTimestamp   = ConvertTo-AdLabIso (ConvertFrom-AdLabFileTime $_.lastLogonTimestamp)
                WhenCreated          = ConvertTo-AdLabIso $_.whenCreated
                PasswordNeverExpires = [bool]$_.PasswordNeverExpires
                PasswordNotRequired  = [bool]$_.PasswordNotRequired
                AdminCount           = [int]$_.adminCount
                HasSpn               = @($_.servicePrincipalName).Count -gt 0
            }
        }
    $computers = Get-ADComputer @ad -Filter * -Properties lastLogonTimestamp, OperatingSystem | ForEach-Object {
        [pscustomobject]@{
            Name               = $_.Name
            Enabled            = [bool]$_.Enabled
            OperatingSystem    = $_.OperatingSystem
            LastLogonTimestamp = ConvertTo-AdLabIso (ConvertFrom-AdLabFileTime $_.lastLogonTimestamp)
        }
    }

    [pscustomobject]@{
        SchemaVersion   = 1
        CollectedAt     = ConvertTo-AdLabIso (Get-Date)
        Domain          = [pscustomobject]@{
            DnsRoot               = $domain.DNSRoot
            DomainMode            = [string]$domain.DomainMode
            ForestMode            = [string]$forest.ForestMode
            BuiltinAdministrator  = $admin.SamAccountName
            GuestEnabled          = [bool]$guest.Enabled
            KrbtgtPasswordLastSet = ConvertTo-AdLabIso (ConvertFrom-AdLabFileTime $krbtgt.pwdLastSet)
            RecycleBinEnabled     = @($recycle.EnabledScopes).Count -gt 0
            MinPasswordLength     = [int]$policy.MinPasswordLength
            LockoutThreshold      = [int]$policy.LockoutThreshold
        }
        ProtectedGroups = @($groups)
        Users           = @($users)
        Computers       = @($computers)
    }
}

Export-ModuleMember -Function ConvertTo-AdLabAscii, ConvertTo-AdLabSamAccountName, Get-AdLabUniqueSamAccountName,
    Get-AdLabOuPlan, New-AdLabUserPlan, ConvertFrom-AdLabFileTime, Test-AdLabHygiene, ConvertTo-AdLabMarkdown,
    Invoke-AdLabProvisioning, Export-AdLabSnapshot
