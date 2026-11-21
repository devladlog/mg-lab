Set-StrictMode -Version Latest

# ---------------------------------------------------------------------------------------------------------------
# SecLab: a read-only security baseline check for the lab servers, a remediation PLAN you can read first, and
# apply / roll-back functions with -WhatIf. Windows PowerShell 5.1 and PowerShell 7.
# Limits and defaults that come from Microsoft Learn are constants here; OUR policy lives in sec-lab.json.
# ---------------------------------------------------------------------------------------------------------------

$script:Severity = @{ High = 0; Medium = 1; Low = 2; Info = 3 }
$script:ProcessCreationGuid = '{0CCE922B-69AE-11D9-BED3-505054503030}'   # Audit Process Creation (Learn: auditpol / security baseline)
$script:LapsPolicyKey = 'HKLM\Software\Microsoft\Windows\CurrentVersion\Policies\LAPS'   # Learn: LAPS Group Policy registry root

function New-SecFinding {
    param([string] $Target, [string] $Severity, [string] $Check, [string] $Message, [string] $Fix = '')
    [pscustomobject]@{ Severity = $Severity; Target = $Target; Check = $Check; Message = $Message; Fix = $Fix }
}

function Get-SecProp {
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] }; return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    $Default
}

function Read-SecLabConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $c = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ((Get-SecProp $c 'SchemaVersion') -ne 1) { throw "Unsupported SchemaVersion in '$Path' (expected 1)." }
    foreach ($k in 'Policy', 'Targets', 'Laps') { if (-not (Get-SecProp $c $k)) { throw "'$Path' is missing '$k'." } }
    $names = @($c.Targets | ForEach-Object { ([string]$_.Name).ToUpperInvariant() })
    $dupe = @($names | Group-Object | Where-Object Count -gt 1 | ForEach-Object Name)
    if ($dupe.Count) { throw "Duplicate target(s) in '$Path': $($dupe -join ', ')." }
    $lm = [int](Get-SecProp $c.Policy 'MinLmCompatibilityLevel' 5)
    if ($lm -lt 0 -or $lm -gt 5) { throw 'MinLmCompatibilityLevel must be 0 to 5 (Learn).' }
    $age = [int](Get-SecProp $c.Laps 'PasswordAgeDays' 30)
    if ($age -lt 1 -or $age -gt 365) { throw 'Laps.PasswordAgeDays must be 1 to 365 (Learn).' }
    $len = [int](Get-SecProp $c.Laps 'PasswordLength' 14)
    if ($len -lt 8 -or $len -gt 64) { throw 'Laps.PasswordLength must be 8 to 64 (Learn).' }
    $c
}

# ---------------------------------------------------------------------------------------------------------------
# Collector (runs ON each server; read-only; self-contained)
# ---------------------------------------------------------------------------------------------------------------

$script:Collector = {
    $ErrorActionPreference = 'Stop'
    $errors = New-Object System.Collections.ArrayList
    function Get-RegValue([string] $Path, [string] $Name) {
        try { $v = (Get-ItemProperty -Path $Path -Name $Name -ErrorAction Stop).$Name; return [int]$v } catch { return $null }
    }
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $cs = Get-CimInstance -ClassName Win32_ComputerSystem
    $smb = [ordered]@{ ServerRequireSigning = $null; ClientRequireSigning = $null; Smb1Enabled = $null }
    try {
        $s = Get-SmbServerConfiguration
        $smb.ServerRequireSigning = [bool]$s.RequireSecuritySignature
        $smb.Smb1Enabled = [bool]$s.EnableSMB1Protocol
    } catch { [void]$errors.Add("SmbServer: $($_.Exception.Message)") }
    try { $smb.ClientRequireSigning = [bool](Get-SmbClientConfiguration).RequireSecuritySignature } catch { [void]$errors.Add("SmbClient: $($_.Exception.Message)") }

    $cg = [ordered]@{ ServicesRunning = @(); Error = $null }
    try { $cg.ServicesRunning = @((Get-CimInstance -ClassName Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard).SecurityServicesRunning | ForEach-Object { [int]$_ }) }
    catch { $cg.Error = $_.Exception.Message }

    $audit = [ordered]@{ ProcessCreation = $null; CommandLine = $null }
    try {
        $csv = & auditpol.exe /get /subcategory:'{0CCE922B-69AE-11D9-BED3-505054503030}' /r 2>&1 | Where-Object { $_ -match ',' } | ConvertFrom-Csv
        $audit.ProcessCreation = [string](@($csv)[0].'Inclusion Setting')
    } catch { [void]$errors.Add("auditpol: $($_.Exception.Message)") }
    $audit.CommandLine = Get-RegValue 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit' 'ProcessCreationIncludeCmdLine_Enabled'

    $def = $null
    try {
        $m = Get-MpComputerStatus
        $def = [ordered]@{ AMServiceEnabled = [bool]$m.AMServiceEnabled; RealTimeProtectionEnabled = [bool]$m.RealTimeProtectionEnabled; IsTamperProtected = [bool]$m.IsTamperProtected; AntivirusSignatureAge = [int]$m.AntivirusSignatureAge }
    } catch { [void]$errors.Add("Defender: $($_.Exception.Message)") }

    $isDc = ([int]$cs.DomainRole -ge 4)
    [pscustomobject]@{
        ComputerName    = [string]$env:COMPUTERNAME
        Caption         = [string]$os.Caption
        Build           = [int]$os.BuildNumber
        DomainRole      = [int]$cs.DomainRole
        PartOfDomain    = [bool]$cs.PartOfDomain
        Smb             = [pscustomobject]$smb
        LmCompatibility = Get-RegValue 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa' 'LmCompatibilityLevel'
        WDigest         = Get-RegValue 'HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest' 'UseLogonCredential'
        CredentialGuard = [pscustomobject]$cg
        LdapServerIntegrity = $(if ($isDc) { Get-RegValue 'HKLM:\SYSTEM\CurrentControlSet\Services\NTDS\Parameters' 'LDAPServerIntegrity' } else { $null })
        Audit           = [pscustomobject]$audit
        Defender        = $(if ($def) { [pscustomobject]$def } else { $null })
        Laps            = [pscustomobject]@{
            BackupDirectory = Get-RegValue 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\LAPS' 'BackupDirectory'
            ModuleAvailable = [bool](Get-Command -Name Get-LapsADPassword -ErrorAction SilentlyContinue)
        }
        Errors          = @($errors)
    }
}

function Get-SecCollectorScript { $script:Collector }

function Get-SecFacts {
    <# Runs the collector on each computer through Invoke-Command (WinRM). Read-only. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string[]] $ComputerName, [pscredential] $Credential)
    $p = @{ ComputerName = $ComputerName; ScriptBlock = $script:Collector; ErrorAction = 'Stop' }
    if ($Credential) { $p.Credential = $Credential }
    $r = @(Invoke-Command @p)
    foreach ($x in $r) {
        $x | Select-Object -Property * -ExcludeProperty PSComputerName, RunspaceId, PSShowComputerName
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Rules (pure)
# ---------------------------------------------------------------------------------------------------------------

function Test-SecHost {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Facts, [Parameter(Mandatory)] $Config)
    $out = New-Object System.Collections.ArrayList
    $pol = $Config.Policy
    $n = [string]$Facts.ComputerName
    $isDc = ([int]$Facts.DomainRole -ge 4)
    $smb = $Facts.Smb

    # --- SMB -------------------------------------------------------------------------------------------------
    if ($true -eq (Get-SecProp $smb 'Smb1Enabled')) {
        [void]$out.Add((New-SecFinding $n High 'Smb1Enabled' 'The SMB 1 server protocol is enabled. Disable it (Set-SmbServerConfiguration -EnableSMB1Protocol $false).' 'DisableSmb1'))
    }
    if ($false -eq (Get-SecProp $smb 'ServerRequireSigning') -and [bool](Get-SecProp $pol 'RequireSmbServerSigning' $true)) {
        [void]$out.Add((New-SecFinding $n Medium 'SmbServerSigningNotRequired' 'Inbound SMB signing is not required (policy: required). Learn: signing protects against tampering and relay; requiring it also disables guest access, so check third-party clients first.' 'RequireSmbServerSigning'))
    }
    if ($false -eq (Get-SecProp $smb 'ClientRequireSigning') -and [bool](Get-SecProp $pol 'RequireSmbClientSigning' $true)) {
        [void]$out.Add((New-SecFinding $n Low 'SmbClientSigningNotRequired' 'Outbound SMB signing is not required (policy: required). Windows Server 2025 requires outbound signing by default (Learn), so this server was changed or is older.'))
    }

    # --- NTLM ------------------------------------------------------------------------------------------------
    $lm = Get-SecProp $Facts 'LmCompatibility'
    $min = [int](Get-SecProp $pol 'MinLmCompatibilityLevel' 5)
    if ($null -eq $lm) {
        [void]$out.Add((New-SecFinding $n Info 'LmCompatibilityNotSet' "LmCompatibilityLevel is not set in the registry, so the OS default applies; policy wants level $min."))
    }
    elseif ([int]$lm -lt 3) {
        [void]$out.Add((New-SecFinding $n High 'LmCompatibilityWeak' "LmCompatibilityLevel is ${lm}: clients send LM or NTLM responses (levels 0 to 2, Learn). Policy wants $min." 'LmCompat'))
    }
    elseif ([int]$lm -lt $min) {
        [void]$out.Add((New-SecFinding $n Medium 'LmCompatibilityBelowPolicy' "LmCompatibilityLevel is $lm, policy wants $min. Level 5 makes domain controllers refuse LM and NTLM (NTLMv2 only, Learn): audit NTLM use first." 'LmCompat'))
    }

    # --- credentials in memory -------------------------------------------------------------------------------
    if ((Get-SecProp $Facts 'WDigest') -eq 1) {
        [void]$out.Add((New-SecFinding $n High 'WDigestEnabled' 'WDigest UseLogonCredential is 1: LSASS keeps a copy of the plaintext password (Learn: recommended state is disabled).' 'WDigestOff'))
    }
    $cgRunning = @((Get-SecProp $Facts.CredentialGuard 'ServicesRunning' @())) -contains 1
    if (-not $cgRunning) {
        if ($isDc) {
            [void]$out.Add((New-SecFinding $n Info 'CredentialGuardNotRunningOnDc' 'Credential Guard is not running. Learn: default enablement on Windows Server 2025 skips domain controllers.'))
        }
        else {
            [void]$out.Add((New-SecFinding $n Medium 'CredentialGuardNotRunning' 'Credential Guard is not running. Learn: it is on by default on Windows Server 2025 for domain-joined non-DC servers that meet the hardware requirements (VBS, Secure Boot; a Hyper-V VM must be generation 2) and are not explicitly disabled.'))
        }
    }

    # --- LDAP signing (domain controllers only) --------------------------------------------------------------
    if ($isDc) {
        $ldap = Get-SecProp $Facts 'LdapServerIntegrity'
        if ($null -eq $ldap) {
            [void]$out.Add((New-SecFinding $n Info 'LdapSigningNotInRegistry' 'No LDAPServerIntegrity value on this domain controller. Not a finding by itself: Learn says Windows Server 2025 requires LDAP signing by default for new deployments, and a missing policy on an upgraded DC takes that default. Check the Group Policy result instead.'))
        }
        elseif ([int]$ldap -eq 0) {
            [void]$out.Add((New-SecFinding $n High 'LdapSigningNotRequired' 'LDAPServerIntegrity is 0: the domain controller accepts unsigned LDAP binds (Learn: set Require signing, check clients first).'))
        }
        elseif ([int]$ldap -ne 2) {
            [void]$out.Add((New-SecFinding $n Medium 'LdapSigningNegotiated' "LDAPServerIntegrity is $ldap, not 2 (Require signing)."))
        }
    }

    # --- audit policy ----------------------------------------------------------------------------------------
    $pc = [string](Get-SecProp $Facts.Audit 'ProcessCreation' '')
    if ([bool](Get-SecProp $pol 'RequireProcessCreationAudit' $true)) {
        if (-not $pc) {
            [void]$out.Add((New-SecFinding $n Info 'ProcessCreationUnknown' 'Could not read the Process Creation audit setting (auditpol output is localized; see Errors).'))
        }
        elseif ($pc -notmatch 'Success') {
            [void]$out.Add((New-SecFinding $n Medium 'ProcessCreationNotAudited' "Audit Process Creation is '$pc'. Without it there is no event 4688 (Learn)." 'AuditProcessCreation'))
        }
        if ($null -eq (Get-SecProp $Facts.Audit 'CommandLine') -or (Get-SecProp $Facts.Audit 'CommandLine') -ne 1) {
            [void]$out.Add((New-SecFinding $n Medium 'CommandLineNotLogged' 'Include command line in process creation events is not enabled (Learn: off by default). Once on, anyone who can read the Security log sees every command line, passwords included if someone typed them.' 'ProcessCreationCmdLine'))
        }
    }

    # --- Defender --------------------------------------------------------------------------------------------
    $d = Get-SecProp $Facts 'Defender'
    if ($null -eq $d) {
        [void]$out.Add((New-SecFinding $n High 'DefenderNotReadable' 'Get-MpComputerStatus returned nothing: Microsoft Defender Antivirus is missing, disabled or replaced.'))
    }
    else {
        if (-not (Get-SecProp $d 'RealTimeProtectionEnabled')) { [void]$out.Add((New-SecFinding $n High 'DefenderRealTimeOff' 'Real-time protection is off.')) }
        if (-not (Get-SecProp $d 'IsTamperProtected')) { [void]$out.Add((New-SecFinding $n Low 'DefenderTamperProtectionOff' 'Tamper protection is off (it cannot be changed with PowerShell, Learn).')) }
        $maxAge = [int](Get-SecProp $pol 'DefenderSignatureMaxAgeDays' 7)
        if ([int](Get-SecProp $d 'AntivirusSignatureAge' 0) -gt $maxAge) {
            [void]$out.Add((New-SecFinding $n Medium 'DefenderSignaturesOld' "Antivirus signatures are $($d.AntivirusSignatureAge) days old (policy: $maxAge)."))
        }
    }

    # --- Windows LAPS ----------------------------------------------------------------------------------------
    if (-not $isDc) {
        $bd = Get-SecProp $Facts.Laps 'BackupDirectory'
        if ($bd -ne 2) {
            [void]$out.Add((New-SecFinding $n Medium 'LapsNotBackingUpToAd' "No Windows LAPS Group Policy backing up to Active Directory (BackupDirectory is $(if ($null -eq $bd) { 'not set' } else { $bd }); Learn: 0 disabled, 1 Entra ID, 2 Active Directory, default disabled). Every server may share one local administrator password." 'LapsGpo'))
        }
    }
    foreach ($e in @(Get-SecProp $Facts 'Errors' @())) { [void]$out.Add((New-SecFinding $n Info 'CollectorError' ([string]$e))) }
    @($out | Sort-Object { $script:Severity[$_.Severity] }, Check)
}

function ConvertTo-SecMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [object[]] $Facts, [object[]] $Findings = @())
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('# Security baseline check')
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('| Server | OS | Domain role | SMB sign (srv/cli) | SMB1 | LmCompat | WDigest | Cred Guard | Proc. audit | Defender RT | LAPS |')
    [void]$sb.AppendLine('|---|---|---|---|---|---|---|---|---|---|---|')
    foreach ($f in $Facts) {
        $cg = if (@((Get-SecProp $f.CredentialGuard 'ServicesRunning' @())) -contains 1) { 'running' } else { 'no' }
        $d = Get-SecProp $f 'Defender'
        $rt = if ($d -and $d.RealTimeProtectionEnabled) { 'on' } else { 'off' }
        $lm = Get-SecProp $f 'LmCompatibility'
        $wd = Get-SecProp $f 'WDigest'
        $row = '| {0} | {1} | {2} | {3}/{4} | {5} | {6} | {7} | {8} | {9} | {10} | {11} |' -f $f.ComputerName, $f.Caption, $f.DomainRole,
        $f.Smb.ServerRequireSigning, $f.Smb.ClientRequireSigning, $f.Smb.Smb1Enabled,
        $(if ($null -eq $lm) { 'not set' } else { $lm }), $(if ($null -eq $wd) { 'not set' } else { $wd }), $cg,
        (Get-SecProp $f.Audit 'ProcessCreation' '?'), $rt, $(if ($f.Laps.BackupDirectory -eq 2) { 'AD' } else { 'no' })
        [void]$sb.AppendLine($row)
    }
    [void]$sb.AppendLine()
    [void]$sb.AppendLine('## Findings')
    [void]$sb.AppendLine()
    if (-not @($Findings).Count) { [void]$sb.AppendLine('None.') }
    else {
        [void]$sb.AppendLine('| Severity | Target | Check | Message |')
        [void]$sb.AppendLine('|---|---|---|---|')
        foreach ($x in $Findings) { [void]$sb.AppendLine(('| {0} | {1} | {2} | {3} |' -f $x.Severity, $x.Target, $x.Check, ($x.Message -replace '\|', '/'))) }
    }
    $sb.ToString()
}

# ---------------------------------------------------------------------------------------------------------------
# Remediation: a plan first (pure), then apply (-WhatIf), and a roll-back plan
# ---------------------------------------------------------------------------------------------------------------

function Get-SecRemediationPlan {
    <#
    .SYNOPSIS
    Pure. One step per (target, fix) found in the findings. A step carries the value we READ before (Before), so it can be rolled back.
    LmCompat is a Risky step and is left out unless -IncludeRisky.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [object[]] $Findings, [Parameter(Mandatory)] $Config, [object[]] $Facts = @(), [switch] $IncludeRisky)
    $by = @{}
    foreach ($f in $Facts) { $by[[string]$f.ComputerName] = $f }
    $steps = New-Object System.Collections.ArrayList
    $cat = @{
        DisableSmb1             = { param($b) @{ Kind = 'SmbServer'; Property = 'EnableSMB1Protocol'; Value = $false; Before = $b.Smb1; Risky = $false; Why = 'Turn the SMB 1 server protocol off.' } }
        RequireSmbServerSigning = { param($b) @{ Kind = 'SmbServer'; Property = 'RequireSecuritySignature'; Value = $true; Before = $b.SmbSign; Risky = $false; Why = 'Require inbound SMB signing (guest access stops working).' } }
        LmCompat                = { param($b) @{ Kind = 'Registry'; Path = 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa'; Name = 'LmCompatibilityLevel'; Value = [int](Get-SecProp $Config.Policy 'MinLmCompatibilityLevel' 5); Type = 'DWord'; Before = $b.Lm; Risky = $true; Why = 'NTLMv2 only: anything still on LM or NTLM stops authenticating.' } }
        WDigestOff              = { param($b) @{ Kind = 'Registry'; Path = 'HKLM:\SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest'; Name = 'UseLogonCredential'; Value = 0; Type = 'DWord'; Before = $b.WDigest; Risky = $false; Why = 'Stop LSASS from keeping the plaintext password.' } }
        AuditProcessCreation    = { param($b) @{ Kind = 'AuditPol'; Subcategory = $script:ProcessCreationGuid; Value = 'enable'; Before = $b.Audit; Risky = $false; Why = 'Audit Process Creation, success (event 4688).' } }
        ProcessCreationCmdLine  = { param($b) @{ Kind = 'Registry'; Path = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Audit'; Name = 'ProcessCreationIncludeCmdLine_Enabled'; Value = 1; Type = 'DWord'; Before = $b.CmdLine; Risky = $false; Why = 'Include the command line in event 4688 (readable by anyone who can read the Security log).' } }
    }
    foreach ($f in @($Findings | Where-Object { $_.Fix -and $cat.ContainsKey($_.Fix) } | Sort-Object Target, Fix -Unique)) {
        $fx = $by[[string]$f.Target]
        $b = @{ Smb1 = $null; SmbSign = $null; Lm = $null; WDigest = $null; Audit = $null; CmdLine = $null }
        if ($fx) {
            $b.Smb1 = Get-SecProp $fx.Smb 'Smb1Enabled'; $b.SmbSign = Get-SecProp $fx.Smb 'ServerRequireSigning'
            $b.Lm = Get-SecProp $fx 'LmCompatibility'; $b.WDigest = Get-SecProp $fx 'WDigest'
            $b.Audit = Get-SecProp $fx.Audit 'ProcessCreation'; $b.CmdLine = Get-SecProp $fx.Audit 'CommandLine'
        }
        $s = & $cat[$f.Fix] $b
        if ($s.Risky -and -not $IncludeRisky) { continue }
        [void]$steps.Add([pscustomobject](@{ Target = [string]$f.Target; Fix = [string]$f.Fix } + $s))
    }
    $steps
}

function Get-SecRollbackPlan {
    <# Pure. Reverse of a remediation plan, from the Before values. A step without a known Before value is returned with Kind 'Manual'. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [object[]] $Plan)
    $out = New-Object System.Collections.ArrayList
    foreach ($s in $Plan) {
        $h = @{}
        foreach ($p in $s.PSObject.Properties) { $h[$p.Name] = $p.Value }
        $h.Fix = "Undo-$($s.Fix)"
        switch ($s.Kind) {
            'Registry' {
                if ($null -eq $s.Before) { $h.Remove = $true; $h.Value = $null; $h.Why = "Remove the value again (it did not exist before)." }
                else { $h.Value = $s.Before; $h.Why = "Put the old value $($s.Before) back." }
            }
            'SmbServer' {
                if ($null -eq $s.Before) { $h.Kind = 'Manual'; $h.Why = 'Old value unknown.' } else { $h.Value = [bool]$s.Before; $h.Why = "Put the old value $($s.Before) back." }
            }
            'AuditPol' { $h.Value = 'disable'; $h.Why = 'Process Creation was not audited before (Before: ' + [string]$s.Before + '): turn success auditing off again.' }
            default { $h.Kind = 'Manual' }
        }
        [void]$out.Add([pscustomobject]$h)
    }
    $out
}

# Runs ON the target, one step. Self-contained.
$script:ApplyStep = {
    param($Step)
    $ErrorActionPreference = 'Stop'
    switch ($Step.Kind) {
        'Registry' {
            if (-not (Test-Path -LiteralPath $Step.Path)) { New-Item -Path $Step.Path -Force | Out-Null }
            if ($Step.Remove) { Remove-ItemProperty -Path $Step.Path -Name $Step.Name -ErrorAction SilentlyContinue }
            else { New-ItemProperty -Path $Step.Path -Name $Step.Name -Value $Step.Value -PropertyType $Step.Type -Force | Out-Null }
        }
        'SmbServer' {
            $a = @{ Force = $true }
            $a[$Step.Property] = [bool]$Step.Value
            Set-SmbServerConfiguration @a
        }
        'AuditPol' {
            $o = & auditpol.exe /set /subcategory:$($Step.Subcategory) /success:$($Step.Value)
            if ($LASTEXITCODE -ne 0) { throw "auditpol failed: $o" }
        }
        default { throw "Step kind '$($Step.Kind)' cannot be applied." }
    }
}

function Invoke-SecRemediation {
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)] [object[]] $Plan, [pscredential] $Credential)
    foreach ($s in $Plan) {
        if ($s.Kind -eq 'Manual') { Write-Warning "$($s.Target): $($s.Fix) needs a manual step ($($s.Why))."; continue }
        if (-not $PSCmdlet.ShouldProcess("$($s.Target)", "$($s.Fix): $($s.Why)")) { continue }
        $p = @{ ComputerName = $s.Target; ScriptBlock = $script:ApplyStep; ArgumentList = @($s); ErrorAction = 'Stop' }
        if ($Credential) { $p.Credential = $Credential }
        Invoke-Command @p
        [pscustomobject]@{ Target = $s.Target; Fix = $s.Fix; Result = 'Applied' }
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Windows LAPS in Active Directory: plan, then apply
# ---------------------------------------------------------------------------------------------------------------

function Get-SecLapsPlan {
    <#
    .SYNOPSIS
    Pure. The Windows LAPS rollout as ordered steps. Update-LapsADSchema is a one-time, forest-wide change (Learn) that
    we treat as irreversible, so the step is marked Irreversible and is skipped when the schema already has it.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Config, [Parameter(Mandatory)] [bool] $SchemaPresent, [Parameter(Mandatory)] [string] $DomainDn)
    $l = $Config.Laps
    $ou = [string](Get-SecProp $l 'OuName' '')
    if (-not $ou) { throw 'Laps.OuName is required.' }
    $ouDn = "OU=$ou,$DomainDn"
    $gpo = [string](Get-SecProp $l 'GpoName' 'MGLab - Windows LAPS')
    $steps = New-Object System.Collections.ArrayList
    if (-not $SchemaPresent) {
        [void]$steps.Add([pscustomobject]@{ Order = 1; Action = 'Schema'; Cmdlet = 'Update-LapsADSchema'; Irreversible = $true; Parameters = [ordered]@{}; Why = 'Adds the msLAPS-* attributes to the forest schema: a one-time operation for the entire forest (Learn). Treat it as irreversible.' })
    }
    [void]$steps.Add([pscustomobject]@{ Order = 2; Action = 'OuPermission'; Cmdlet = 'Set-LapsADComputerSelfPermission'; Irreversible = $false; Parameters = [ordered]@{ Identity = $ouDn }; Why = 'Lets computers in the OU update their own password attributes (Learn).' })
    [void]$steps.Add([pscustomobject]@{ Order = 3; Action = 'Gpo'; Cmdlet = 'New-GPO'; Irreversible = $false; Parameters = [ordered]@{ Name = $gpo }; Why = 'Policy container (skipped if it exists).' })
    $vals = @(
        @{ Name = 'BackupDirectory'; Value = [int](Get-SecProp $l 'BackupDirectory' 2) },
        @{ Name = 'PasswordAgeDays'; Value = [int](Get-SecProp $l 'PasswordAgeDays' 30) },
        @{ Name = 'PasswordLength'; Value = [int](Get-SecProp $l 'PasswordLength' 14) }
    )
    $adm = [string](Get-SecProp $l 'AdministratorAccountName' '')
    foreach ($v in $vals) {
        [void]$steps.Add([pscustomobject]@{ Order = 4; Action = 'GpoValue'; Cmdlet = 'Set-GPRegistryValue'; Irreversible = $false; Parameters = [ordered]@{ Name = $gpo; Key = $script:LapsPolicyKey; ValueName = $v.Name; Type = 'DWord'; Value = $v.Value }; Why = "LAPS $($v.Name) = $($v.Value) in the Group Policy registry root (Learn)." })
    }
    if ($adm) {
        [void]$steps.Add([pscustomobject]@{ Order = 4; Action = 'GpoValue'; Cmdlet = 'Set-GPRegistryValue'; Irreversible = $false; Parameters = [ordered]@{ Name = $gpo; Key = $script:LapsPolicyKey; ValueName = 'AdministratorAccountName'; Type = 'String'; Value = $adm }; Why = 'Manage a custom local administrator account; Windows LAPS does not create it (Learn).' })
    }
    [void]$steps.Add([pscustomobject]@{ Order = 5; Action = 'Link'; Cmdlet = 'New-GPLink'; Irreversible = $false; Parameters = [ordered]@{ Name = $gpo; Target = $ouDn }; Why = 'Link the GPO to the OU (skipped if already linked).' })
    $steps
}

function Invoke-SecLapsPlan {
    <# Applies Get-SecLapsPlan. The irreversible schema step runs only with -AllowSchemaUpdate. Idempotent for the GPO and link. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param([Parameter(Mandatory)] [object[]] $Plan, [switch] $AllowSchemaUpdate)
    foreach ($s in $Plan) {
        $p = @{}
        foreach ($k in $s.Parameters.Keys) { $p[$k] = $s.Parameters[$k] }
        $target = "$($s.Action): $($s.Cmdlet)"
        switch ($s.Action) {
            'Schema' {
                if (-not $AllowSchemaUpdate) { Write-Warning 'Skipping Update-LapsADSchema: it is forest-wide and irreversible. Re-run with -AllowSchemaUpdate.'; continue }
                if ($PSCmdlet.ShouldProcess($target, $s.Why)) { Update-LapsADSchema -Confirm:$false }
            }
            'OuPermission' { if ($PSCmdlet.ShouldProcess($target, $s.Why)) { Set-LapsADComputerSelfPermission @p | Out-Null } }
            'Gpo' {
                if (Get-GPO -Name $p.Name -ErrorAction SilentlyContinue) { Write-Verbose "GPO '$($p.Name)' exists." }
                elseif ($PSCmdlet.ShouldProcess($target, $s.Why)) { New-GPO @p | Out-Null }
            }
            'GpoValue' { if ($PSCmdlet.ShouldProcess($target, $s.Why)) { Set-GPRegistryValue @p | Out-Null } }
            'Link' {
                $linked = @((Get-GPInheritance -Target $p.Target).GpoLinks | Where-Object { $_.DisplayName -eq $p.Name })
                if ($linked.Count) { Write-Verbose "GPO '$($p.Name)' is already linked." }
                elseif ($PSCmdlet.ShouldProcess($target, $s.Why)) { New-GPLink @p | Out-Null }
            }
        }
    }
}

Export-ModuleMember -Function Read-SecLabConfig, Get-SecCollectorScript, Get-SecFacts, Test-SecHost, ConvertTo-SecMarkdown,
    Get-SecRemediationPlan, Get-SecRollbackPlan, Invoke-SecRemediation, Get-SecLapsPlan, Invoke-SecLapsPlan
