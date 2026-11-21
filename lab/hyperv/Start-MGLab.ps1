#Requires -RunAsAdministrator
#Requires -Version 5.1
<#
.SYNOPSIS
  Builds the MG Lab Hyper-V lab on this PC: NAT switch, Windows Server 2025 evaluation VMs,
  the lab.contoso.com domain and SQL Server 2022 (Developer edition).

.DESCRIPTION
  Safe to re-run: every stage checks what already exists and skips it.
  Stages: host check -> Hyper-V -> lab drive -> lab password -> switch -> media -> base disks -> VMs ->
          guest network -> domain -> joins -> SQL Server -> summary.
  Everything goes under \MGLab on the fixed drive with the most free space (or LabRoot in lab.config.psd1).
  The lab Administrator password is generated here and stored DPAPI-encrypted for your Windows user only
  (<LabRoot>\secrets\lab-admin.xml). It is never printed. To read it yourself:
      (Import-Clixml <LabRoot>\secrets\lab-admin.xml).GetNetworkCredential().Password

.PARAMETER NoDomain   Create and network the VMs but don't promote a DC or join anything.
.PARAMETER NoSql      Skip the SQL Server install.
.PARAMETER Only       Build only these VM names (e.g. -Only CON-DC01).
.PARAMETER CheckOnly  Run the host check and print the plan, change nothing.
#>
[CmdletBinding()]
param(
    [string]$Config = (Join-Path $PSScriptRoot 'lab.config.psd1'),
    [switch]$NoDomain,
    [switch]$NoSql,
    [string[]]$Only,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$cfg = Import-PowerShellDataFile -Path $Config

function Write-Stage([string]$Text) { Write-Host "`n=== $Text ===" -ForegroundColor Cyan }
function Write-Ok([string]$Text)    { Write-Host "  [ok] $Text" -ForegroundColor Green }
function Write-Skip([string]$Text)  { Write-Host "  [skip] $Text" -ForegroundColor DarkGray }
function Write-Warn2([string]$Text) { Write-Host "  [!] $Text" -ForegroundColor Yellow }

# ---------------------------------------------------------------- host check
Write-Stage 'Host check'
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
$freeRamGB = [math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 1)
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
Write-Host ("  {0} | {1} | {2} logical CPUs | RAM {3} GB (free {4} GB)" -f $os.Caption, $cpu.Name.Trim(), $cs.NumberOfLogicalProcessors, $ramGB, $freeRamGB)
if ($os.Caption -match 'Home') { throw 'Windows Home has no Hyper-V. Pro, Enterprise or Education is required.' }

$vms = @($cfg.VMs | Where-Object { -not $Only -or $Only -contains $_.Name })
# Windows PowerShell 5.1's Measure-Object can't read hashtable keys, so enumerate the values first.
$planMaxGB = ($vms.MaxGB | Measure-Object -Sum).Sum
$planStartGB = ($vms.StartupGB | Measure-Object -Sum).Sum
Write-Host ("  Plan: {0} VMs, startup RAM {1} GB, max RAM {2} GB" -f $vms.Count, $planStartGB, $planMaxGB)
if ($planStartGB -gt ($ramGB - 6)) { Write-Warn2 'Startup RAM leaves less than 6 GB for Windows and the recording apps. Lower StartupGB in lab.config.psd1 or use -Only.' }

$hv = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
if ($hv.State -ne 'Enabled') {
    if ($cs.HypervisorPresent -eq $false -and $cpu.VirtualizationFirmwareEnabled -eq $false) {
        throw 'Virtualization is disabled in the BIOS/UEFI. Enable Intel VT-x / AMD-V (SVM), then run again.'
    }
    if ($CheckOnly) { Write-Warn2 'Hyper-V is not enabled yet (it will be enabled on a real run).' }
    else {
        Write-Host '  Enabling Hyper-V (needs one restart)...'
        Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart | Out-Null
        Write-Warn2 'Hyper-V enabled. Restart Windows, then run this script again.'
        exit 3010
    }
} else { Write-Ok 'Hyper-V enabled' }

# ---------------------------------------------------------------- lab drive
Write-Stage 'Lab drive'
if ($cfg.LabRoot -and $cfg.LabRoot -ne 'auto') { $LabRoot = $cfg.LabRoot }
else {
    $vol = Get-Volume | Where-Object { $_.DriveType -eq 'Fixed' -and $_.DriveLetter -and $_.FileSystem -in 'NTFS', 'ReFS' } |
        Sort-Object SizeRemaining -Descending | Select-Object -First 1
    if (-not $vol) { throw 'No fixed NTFS/ReFS drive found.' }
    $LabRoot = "$($vol.DriveLetter):\MGLab"
}
$drive = Get-Volume -DriveLetter $LabRoot.Substring(0, 1)
$freeGB = [math]::Round($drive.SizeRemaining / 1GB)
Write-Host ("  Lab root: {0} ({1} GB free on {2}:)" -f $LabRoot, $freeGB, $drive.DriveLetter)
Get-Volume | Where-Object { $_.DriveType -eq 'Fixed' -and $_.DriveLetter } | ForEach-Object {
    Write-Host ("    {0}: {1,6:N0} GB free of {2:N0} GB" -f $_.DriveLetter, ($_.SizeRemaining / 1GB), ($_.Size / 1GB))
}
if ($freeGB -lt $cfg.MinFreeGB) { throw "Only $freeGB GB free on the lab drive; at least $($cfg.MinFreeGB) GB is needed." }
if ($CheckOnly) { Write-Ok 'Check finished. Nothing was changed.'; return }

$P = @{ Iso = "$LabRoot\iso"; Base = "$LabRoot\base"; Vms = "$LabRoot\vms"; Secrets = "$LabRoot\secrets"; Logs = "$LabRoot\logs" }
$P.Values | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }
Start-Transcript -Path ("$($P.Logs)\build-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date)) | Out-Null
# Keep the password out of the transcript: it only ever lives in variables.

# ---------------------------------------------------------------- password
Write-Stage 'Lab password'
$secretFile = "$($P.Secrets)\lab-admin.xml"
if (-not (Test-Path $secretFile)) {
    $sets = 'ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnopqrstuvwxyz', '23456789', '!#%+=?@'
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $pick = { param($s) $b = New-Object byte[] 1; $rng.GetBytes($b); $s[$b[0] % $s.Length] }
    $chars = @(); foreach ($s in $sets) { 1..2 | ForEach-Object { $chars += & $pick $s } }
    $all = -join $sets; while ($chars.Count -lt 20) { $chars += & $pick $all }
    $plain = -join ($chars | Sort-Object { $b = New-Object byte[] 4; $rng.GetBytes($b); [BitConverter]::ToUInt32($b, 0) })
    New-Object PSCredential ('Administrator', (ConvertTo-SecureString $plain -AsPlainText -Force)) | Export-Clixml -Path $secretFile
    Remove-Variable plain
    Write-Ok "Generated and saved (DPAPI, your user only): $secretFile"
} else { Write-Skip 'Password already exists' }
$localCred = Import-Clixml $secretFile
$labPass = $localCred.Password
$domainCred = New-Object PSCredential ("$($cfg.NetBIOS)\Administrator", $labPass)
function Get-PlainPass { $localCred.GetNetworkCredential().Password }

# ---------------------------------------------------------------- switch + NAT
Write-Stage 'Network'
$sw = $cfg.Switch
$natPrefix = "$($sw.Prefix).0/$($sw.PrefixLength)"
if (-not (Get-VMSwitch -Name $sw.Name -ErrorAction SilentlyContinue)) {
    New-VMSwitch -Name $sw.Name -SwitchType Internal | Out-Null
    Write-Ok "Switch $($sw.Name) created"
} else { Write-Skip "Switch $($sw.Name) exists" }
$ifAlias = "vEthernet ($($sw.Name))"
if (-not (Get-NetIPAddress -InterfaceAlias $ifAlias -IPAddress $sw.Gateway -ErrorAction SilentlyContinue)) {
    New-NetIPAddress -InterfaceAlias $ifAlias -IPAddress $sw.Gateway -PrefixLength $sw.PrefixLength | Out-Null
    Write-Ok "Host gateway $($sw.Gateway) on $ifAlias"
} else { Write-Skip 'Host gateway address exists' }
if (-not (Get-NetNat -Name $sw.Name -ErrorAction SilentlyContinue)) {
    $other = Get-NetNat -ErrorAction SilentlyContinue
    if ($other) { Write-Warn2 "Another NAT exists ($($other.Name -join ', ')). Windows supports one NAT network; adding may fail." }
    New-NetNat -Name $sw.Name -InternalIPInterfaceAddressPrefix $natPrefix | Out-Null
    Write-Ok "NAT $natPrefix"
} else { Write-Skip 'NAT exists' }

# ---------------------------------------------------------------- media
Write-Stage 'Media'
function Get-Download([string]$Url, [string]$Dest, [long]$MinBytes) {
    if ((Test-Path $Dest) -and (Get-Item $Dest).Length -ge $MinBytes) { Write-Skip (Split-Path $Dest -Leaf); return }
    Write-Host "  Downloading $(Split-Path $Dest -Leaf) ..."
    Start-BitsTransfer -Source $Url -Destination $Dest -DisplayName 'MGLab media'
    if ((Get-Item $Dest).Length -lt $MinBytes) { throw "Download of $Dest looks incomplete." }
    Write-Ok (Split-Path $Dest -Leaf)
}
$serverIso = "$($P.Iso)\WindowsServer2025-Eval.iso"
Get-Download $cfg.Media.ServerIso $serverIso 4GB
# Windows 11 Enterprise evaluation (90 days) for client VMs (Role = 'Client'). The Evaluation Center asks you to
# register, so there is no stable direct link: download the x64 ISO yourself and save it as the path below, or put a
# direct URL in Media.Win11Iso. Without it, client VMs are skipped and everything else is built.
$win11Iso = "$($P.Iso)\Win11Ent-Eval.iso"
if (-not (Test-Path $win11Iso) -and $cfg.Media.Win11Iso -match '^https?://') { Get-Download $cfg.Media.Win11Iso $win11Iso 4GB }
if (($vms | Where-Object Role -eq 'Client') -and -not (Test-Path $win11Iso)) {
    Write-Warn2 "No Windows 11 ISO at ${win11Iso}: client VMs are skipped (get it from microsoft.com/evalcenter > Windows 11 Enterprise)."
    $vms = @($vms | Where-Object Role -ne 'Client')
}

# ---------------------------------------------------------------- base disks
Write-Stage 'Base disks'
function Get-PartitionLetter($Part) {
    # Windows may already have auto-mounted the partition; only assign a letter when it has none.
    $p = Get-Partition -DiskNumber $Part.DiskNumber -PartitionNumber $Part.PartitionNumber
    if ([string]$p.DriveLetter -notmatch '^[A-Za-z]$') {
        $p | Add-PartitionAccessPath -AssignDriveLetter
        $p = Get-Partition -DiskNumber $Part.DiskNumber -PartitionNumber $Part.PartitionNumber
    }
    [string]$p.DriveLetter
}
function New-BaseDisk([string]$Kind) {
    $isClient = $Kind -eq 'Win11'
    $iso = if ($isClient) { $win11Iso } else { $serverIso }
    $path = if ($isClient) { "$($P.Base)\win11-enterprise.vhdx" } else { "$($P.Base)\ws2025-$($Kind.ToLower()).vhdx" }
    if (Test-Path $path) {
        # The read-only flag is set only after a base disk is complete, so it doubles as the "finished" marker.
        if ((Get-Item $path).IsReadOnly) { Write-Skip (Split-Path $path -Leaf); return $path }
        Write-Warn2 "Removing unfinished $(Split-Path $path -Leaf) from an interrupted run"
        try { Dismount-VHD -Path $path -ErrorAction Stop } catch { }
        Remove-Item $path -Force
    }
    $img = Mount-DiskImage -ImagePath $iso -PassThru
    try {
        $isoDrive = ($img | Get-Volume).DriveLetter
        $wim = "${isoDrive}:\sources\install.wim"
        $images = Get-WindowsImage -ImagePath $wim
        $want = if ($isClient) {
            $images | Where-Object { $_.ImageName -match 'Enterprise' -and $_.ImageName -notmatch '\bN\b|LTSC' } | Select-Object -First 1
        } else {
            $images | Where-Object { $_.ImageName -match 'Datacenter' -and $_.ImageName -match 'Evaluation' -and
                (($Kind -eq 'Desktop') -eq ($_.ImageName -match 'Desktop')) } | Select-Object -First 1
        }
        if (-not $want) { throw "No Datacenter Evaluation ($Kind) image in the ISO: $($images.ImageName -join '; ')" }
        Write-Host "  Applying '$($want.ImageName)' to $(Split-Path $path -Leaf) (10-20 min)..."
        $vhd = New-VHD -Path $path -SizeBytes $(if ($isClient) { 64GB } else { 60GB }) -Dynamic
        $disk = Mount-VHD -Path $path -Passthru | Get-Disk
        try {
            Initialize-Disk -Number $disk.Number -PartitionStyle GPT
            $efi = New-Partition -DiskNumber $disk.Number -Size 260MB -GptType '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'
            $efi | Format-Volume -FileSystem FAT32 -NewFileSystemLabel System -Confirm:$false | Out-Null
            New-Partition -DiskNumber $disk.Number -Size 16MB -GptType '{e3c9e316-0b5c-4db8-817d-f92df00215ae}' | Out-Null
            $os = New-Partition -DiskNumber $disk.Number -UseMaximumSize -GptType '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}'
            $os | Format-Volume -FileSystem NTFS -NewFileSystemLabel Windows -Confirm:$false | Out-Null
            $s = Get-PartitionLetter $efi
            $w = Get-PartitionLetter $os
            Expand-WindowsImage -ImagePath $wim -Index $want.ImageIndex -ApplyPath "${w}:\" | Out-Null
            & "$env:windir\System32\bcdboot.exe" "${w}:\Windows" /s "${s}:" /f UEFI | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "bcdboot failed ($LASTEXITCODE)" }
            Remove-PartitionAccessPath -DiskNumber $disk.Number -PartitionNumber $efi.PartitionNumber -AccessPath "${s}:\"
        } finally { Dismount-VHD -Path $path }
        Set-ItemProperty -Path $path -Name IsReadOnly -Value $true   # parents of differencing disks must never change
        Write-Ok (Split-Path $path -Leaf)
    } catch { Dismount-DiskImage -ImagePath $iso -ErrorAction SilentlyContinue | Out-Null; if (Test-Path $path) { Remove-Item $path -Force }; throw }
    finally { Dismount-DiskImage -ImagePath $iso -ErrorAction SilentlyContinue | Out-Null }
    return $path
}
$base = @{}
foreach ($kind in ($vms.Image | Sort-Object -Unique)) { $base[$kind] = New-BaseDisk $kind }

# ---------------------------------------------------------------- VMs
Write-Stage 'Virtual machines'
function New-Unattend([string]$Name) {
    $pw = [System.Security.SecurityElement]::Escape((Get-PlainPass))
    @"
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
  <settings pass="specialize">
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <ComputerName>$Name</ComputerName>
      <TimeZone>$($cfg.TimeZone)</TimeZone>
    </component>
    <component name="Microsoft-Windows-TerminalServices-LocalSessionManager" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <fDenyTSConnections>false</fDenyTSConnections>
    </component>
  </settings>
  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <InputLocale>$($cfg.InputLocale)</InputLocale><SystemLocale>$($cfg.Locale)</SystemLocale><UILanguage>$($cfg.Locale)</UILanguage><UserLocale>$($cfg.Locale)</UserLocale>
    </component>
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS">
      <UserAccounts><AdministratorPassword><Value>$pw</Value><PlainText>true</PlainText></AdministratorPassword></UserAccounts>
      <OOBE><HideEULAPage>true</HideEULAPage><SkipMachineOOBE>true</SkipMachineOOBE><ProtectYourPC>3</ProtectYourPC></OOBE>
    </component>
  </settings>
</unattend>
"@
}

foreach ($v in $vms) {
    if (Get-VM -Name $v.Name -ErrorAction SilentlyContinue) { Write-Skip "$($v.Name) exists"; continue }
    $dir = "$($P.Vms)\$($v.Name)"; New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $child = "$dir\$($v.Name).vhdx"
    if (Test-Path $child) {   # left over from an interrupted run (the VM was never registered)
        try { Dismount-VHD -Path $child -ErrorAction Stop } catch { }
        Remove-Item $child -Force
    }
    New-VHD -Path $child -ParentPath $base[$v.Image] -Differencing | Out-Null
    if ($v.DiskGB -gt 64 -or ($v.DiskGB -gt 60 -and $v.Role -ne 'Client')) { Resize-VHD -Path $child -SizeBytes ([int64]$v.DiskGB * 1GB) }
    if ($v.Role -eq 'Client') {
        # Client VMs boot into Windows setup (OOBE) on purpose: the Entra join / Intune enrolment is done there, for real.
        $vmSwitch = if ($v.Switch) { $v.Switch } else { 'Default Switch' }   # Hyper-V's built-in NAT switch has DHCP
        New-VM -Name $v.Name -Generation 2 -VHDPath $child -SwitchName $vmSwitch -MemoryStartupBytes ([int64]($v.StartupGB * 1GB)) -Path $P.Vms | Out-Null
        Set-VM -Name $v.Name -ProcessorCount $v.vCPU -StaticMemory -AutomaticCheckpointsEnabled $false -AutomaticStopAction ShutDown -AutomaticStartAction Nothing
        Set-VMKeyProtector -VMName $v.Name -NewLocalKeyProtector
        Enable-VMTPM -VMName $v.Name                                          # Windows 11 needs TPM 2.0
        Enable-VMIntegrationService -VMName $v.Name -Name 'Guest Service Interface'
        Start-VM -Name $v.Name
        Write-Ok "$($v.Name) created and started at Windows setup (Windows 11, vTPM, $($v.vCPU) vCPU, $($v.StartupGB) GB, switch $vmSwitch)"
        continue
    }
    $disk = Mount-VHD -Path $child -Passthru | Get-Disk
    try {
        $osPart = Get-Partition -DiskNumber $disk.Number | Where-Object { $_.GptType -eq '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}' } | Select-Object -First 1
        $w = Get-PartitionLetter $osPart
        New-Item -ItemType Directory -Force -Path "${w}:\Windows\Panther" | Out-Null
        New-Unattend $v.Name | Set-Content -Path "${w}:\Windows\Panther\unattend.xml" -Encoding UTF8
    } finally { Dismount-VHD -Path $child }
    New-VM -Name $v.Name -Generation 2 -VHDPath $child -SwitchName $sw.Name -MemoryStartupBytes ([int64]($v.StartupGB * 1GB)) -Path $P.Vms | Out-Null
    Set-VM -Name $v.Name -ProcessorCount $v.vCPU -DynamicMemory -MemoryMinimumBytes 512MB -MemoryMaximumBytes ([int64]($v.MaxGB * 1GB)) `
        -AutomaticCheckpointsEnabled $false -AutomaticStopAction ShutDown -AutomaticStartAction Nothing
    Enable-VMIntegrationService -VMName $v.Name -Name 'Guest Service Interface'
    # Hyper-V can't hot-add a DVD drive, so the SQL VM gets an empty one now; the SQL media is inserted later.
    if ($v.Role -eq 'SQL') { Add-VMDvdDrive -VMName $v.Name }
    Start-VM -Name $v.Name
    Write-Ok "$($v.Name) created and started ($($v.Image), $($v.vCPU) vCPU, $($v.StartupGB)-$($v.MaxGB) GB, $($v.DiskGB) GB)"
}

function Wait-Guest([string]$Name, [pscredential[]]$Cred, [int]$Minutes = 20) {
    # Succeeds when any of the credentials works (a DC only accepts the domain account after promotion).
    $until = (Get-Date).AddMinutes($Minutes)
    while ((Get-Date) -lt $until) {
        foreach ($c in $Cred) {
            try { Invoke-Command -VMName $Name -Credential $c -ScriptBlock { $env:COMPUTERNAME } -ErrorAction Stop | Out-Null; return } catch { }
        }
        Start-Sleep -Seconds 15
    }
    throw "$Name did not answer PowerShell Direct within $Minutes minutes (open it in Hyper-V Manager to see why)."
}
function Get-GuestCred([string]$Name) {
    # After promotion/join the domain account works everywhere; before that only the local one.
    foreach ($c in $domainCred, $localCred) {
        try { Invoke-Command -VMName $Name -Credential $c -ScriptBlock { 1 } -ErrorAction Stop | Out-Null; return $c } catch { }
    }
    throw "Neither the domain nor the local Administrator credential works on $Name."
}

# ---------------------------------------------------------------- guest network
Write-Stage 'Guest network and remote access'
$clientVms = @($vms | Where-Object Role -eq 'Client')
$vms = @($vms | Where-Object Role -ne 'Client')   # client VMs are finished by hand at Windows setup
$dcCfg = $cfg.VMs | Where-Object Role -eq 'DC' | Select-Object -First 1
$dcIP = "$($sw.Prefix).$($dcCfg.IP)"
foreach ($v in $vms) {
    Wait-Guest $v.Name $localCred, $domainCred -Minutes 25
    $cred = Get-GuestCred $v.Name
    $ip = "$($sw.Prefix).$($v.IP)"
    $dns = if ($v.Role -eq 'DC' -or $NoDomain) { @('1.1.1.1', '8.8.8.8') } else { @($dcIP) }
    Invoke-Command -VMName $v.Name -Credential $cred -ArgumentList $ip, $sw.PrefixLength, $sw.Gateway, $dns -ScriptBlock {
        param($ip, $len, $gw, $dns)
        $nic = Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -First 1
        if (-not (Get-NetIPAddress -InterfaceIndex $nic.ifIndex -IPAddress $ip -ErrorAction SilentlyContinue)) {
            Set-NetIPInterface -InterfaceIndex $nic.ifIndex -Dhcp Disabled
            Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Remove-NetIPAddress -Confirm:$false
            New-NetIPAddress -InterfaceIndex $nic.ifIndex -IPAddress $ip -PrefixLength $len -DefaultGateway $gw | Out-Null
        }
        if ((Get-CimInstance Win32_ComputerSystem).DomainRole -lt 4) { Set-DnsClientServerAddress -InterfaceIndex $nic.ifIndex -ServerAddresses $dns }
        Remove-Item C:\Windows\Panther\unattend.xml -Force -ErrorAction SilentlyContinue   # it held the first-boot password
        Enable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue
        Set-NetFirewallRule -Name 'FPS-ICMP4-ERQ-In' -Enabled True -ErrorAction SilentlyContinue
        $p = Get-Partition | Where-Object { $_.DriveLetter -eq 'C' }
        $max = ($p | Get-PartitionSupportedSize).SizeMax
        if ($max - $p.Size -gt 1GB) { Resize-Partition -DriveLetter C -Size $max }
    }
    Write-Ok "$($v.Name) $ip"
}

# ---------------------------------------------------------------- domain
if (-not $NoDomain -and ($vms.Name -contains $dcCfg.Name -or (Get-VM $dcCfg.Name -ErrorAction SilentlyContinue))) {
    Write-Stage "Domain $($cfg.Domain)"
    $isDc = Invoke-Command -VMName $dcCfg.Name -Credential (Get-GuestCred $dcCfg.Name) -ScriptBlock { (Get-CimInstance Win32_ComputerSystem).DomainRole -ge 4 }
    if (-not $isDc) {
        Write-Host "  Promoting $($dcCfg.Name) to the first DC of a new forest (reboots, ~10 min)..."
        try { Invoke-Command -VMName $dcCfg.Name -Credential $localCred -ArgumentList $cfg.Domain, $cfg.NetBIOS, $labPass -ScriptBlock {
            param($domain, $netbios, $dsrm)
            Install-WindowsFeature AD-Domain-Services, DNS -IncludeManagementTools | Out-Null
            Install-ADDSForest -DomainName $domain -DomainNetbiosName $netbios -SafeModeAdministratorPassword $dsrm `
                -InstallDns -Force -NoRebootOnCompletion | Out-Null
            Restart-Computer -Force
        } } catch { if ($_.Exception.Message -notmatch 'broken|closed|terminated|disconnect') { throw } }
        Start-Sleep -Seconds 90
        Wait-Guest $dcCfg.Name $domainCred -Minutes 30
        # AD Web Services needs a moment after first boot.
        $until = (Get-Date).AddMinutes(10)
        do { Start-Sleep 15; $ready = Invoke-Command -VMName $dcCfg.Name -Credential $domainCred -ScriptBlock { try { [bool](Get-ADDomain -ErrorAction Stop) } catch { $false } } }
        until ($ready -or (Get-Date) -gt $until)
        Invoke-Command -VMName $dcCfg.Name -Credential $domainCred -ScriptBlock { Set-DnsServerForwarder -IPAddress 1.1.1.1, 8.8.8.8 -ErrorAction SilentlyContinue }
        Write-Ok "$($dcCfg.Name) is the DC for $($cfg.Domain)"
    } else { Write-Skip "$($dcCfg.Name) is already a DC" }

    Write-Stage 'Domain joins'
    foreach ($v in ($vms | Where-Object Role -ne 'DC')) {
        $joined = Invoke-Command -VMName $v.Name -Credential (Get-GuestCred $v.Name) -ScriptBlock { (Get-CimInstance Win32_ComputerSystem).PartOfDomain }
        if ($joined) { Write-Skip "$($v.Name) already joined"; continue }
        try { Invoke-Command -VMName $v.Name -Credential $localCred -ArgumentList $cfg.Domain, $domainCred -ScriptBlock {
            param($domain, $cred)
            Add-Computer -DomainName $domain -Credential $cred -Force
            Restart-Computer -Force
        } } catch { if ($_.Exception.Message -notmatch 'broken|closed|terminated|disconnect') { throw } }
        Start-Sleep -Seconds 45
        Wait-Guest $v.Name $domainCred -Minutes 15
        Write-Ok "$($v.Name) joined $($cfg.Domain)"
    }
}

# ---------------------------------------------------------------- SQL Server
$sqlCfg = $vms | Where-Object Role -eq 'SQL' | Select-Object -First 1
if ($sqlCfg -and -not $NoSql) {
    Write-Stage "SQL Server 2022 Developer on $($sqlCfg.Name)"
    $sqlCred = Get-GuestCred $sqlCfg.Name
    $installed = Invoke-Command -VMName $sqlCfg.Name -Credential $sqlCred -ScriptBlock { [bool](Get-Service MSSQLSERVER -ErrorAction SilentlyContinue) }
    if ($installed) { Write-Skip 'SQL Server already installed' }
    else {
        # Direct ISO download (BITS, resumable, only renamed into place when complete), ~1.1 GB.
        New-Item -ItemType Directory -Force -Path "$($P.Iso)\sql" | Out-Null
        $sqlIsoPath = "$($P.Iso)\sql\SQLServer2022-x64-ENU-Dev.iso"
        Get-Download $cfg.Media.SqlIso $sqlIsoPath 1GB
        $sqlIso = Get-Item $sqlIsoPath
        if (-not (Get-VMDvdDrive -VMName $sqlCfg.Name)) {
            # Only VMs built by an older version of this script lack the drive; adding one needs the VM off.
            Write-Host "  Adding a DVD drive to $($sqlCfg.Name) (restarts it)..."
            Stop-VM -Name $sqlCfg.Name; Add-VMDvdDrive -VMName $sqlCfg.Name; Start-VM -Name $sqlCfg.Name
            Wait-Guest $sqlCfg.Name $sqlCred -Minutes 15
        }
        Get-VMDvdDrive -VMName $sqlCfg.Name | Select-Object -First 1 | Set-VMDvdDrive -Path $sqlIso.FullName
        Write-Host '  Installing the database engine (10-15 min)...'
        $r = Invoke-Command -VMName $sqlCfg.Name -Credential $sqlCred -ArgumentList $labPass, $cfg.NetBIOS -ScriptBlock {
            param($sa, $netbios)
            $setup = Get-Volume | Where-Object DriveType -eq 'CD-ROM' | ForEach-Object { "$($_.DriveLetter):\setup.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $setup) { throw 'SQL setup.exe not found on the DVD drive.' }
            $saPlain = (New-Object PSCredential 'sa', $sa).GetNetworkCredential().Password
            $admins = if ((Get-CimInstance Win32_ComputerSystem).PartOfDomain) { "`"$netbios\Domain Admins`"" } else { 'BUILTIN\Administrators' }
            # 22222-00000-00000-00000-00000 = Developer edition (free, non-production)
            $setupArgs = @('/Q', '/ACTION=Install', '/FEATURES=SQLENGINE', '/INSTANCENAME=MSSQLSERVER', '/IACCEPTSQLSERVERLICENSETERMS',
                '/PID=22222-00000-00000-00000-00000', "/SQLSYSADMINACCOUNTS=$admins", '/SECURITYMODE=SQL', "/SAPWD=$saPlain",
                '/TCPENABLED=1', '/UPDATEENABLED=0', '/SQLSVCSTARTUPTYPE=Automatic')
            $p = Start-Process -FilePath $setup -ArgumentList $setupArgs -Wait -PassThru -NoNewWindow
            New-NetFirewallRule -DisplayName 'SQL Server 1433' -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow -ErrorAction SilentlyContinue | Out-Null
            [pscustomobject]@{ Exit = $p.ExitCode; Running = [bool](Get-Service MSSQLSERVER -ErrorAction SilentlyContinue | Where-Object Status -eq Running) }
        }
        Get-VMDvdDrive -VMName $sqlCfg.Name | Select-Object -First 1 | Set-VMDvdDrive -Path $null
        if (-not $r.Running) { throw "SQL setup exit code $($r.Exit). Logs: C:\Program Files\Microsoft SQL Server\160\Setup Bootstrap\Log on $($sqlCfg.Name)." }
        Write-Ok "SQL Server running on $($sw.Prefix).$($sqlCfg.IP),1433 (logins: sa or $($cfg.NetBIOS)\Administrator)"
    }
}

# ---------------------------------------------------------------- summary
Write-Stage 'MG Lab ready'
Get-VM | Where-Object { $cfg.VMs.Name -contains $_.Name } | ForEach-Object {
    $c = $cfg.VMs | Where-Object Name -eq $_.Name
    [pscustomobject]@{ VM = $_.Name; Role = $c.Role; IP = "$($sw.Prefix).$($c.IP)"; State = $_.State; 'RAM GB' = [math]::Round($_.MemoryAssigned / 1GB, 1) }
} | Format-Table -AutoSize | Out-String | Write-Host
Write-Host "  Domain: $($cfg.Domain)  |  Accounts: Administrator / $($cfg.NetBIOS)\Administrator / sa"
Write-Host "  Password: (Import-Clixml '$secretFile').GetNetworkCredential().Password"
Write-Host "  Connect: mstsc /v:$dcIP   |   SQL: $($sw.Prefix).$($sqlCfg.IP),1433"
Write-Host "  Stop all: .\Stop-MGLab.ps1   |   Start all: .\Start-MGLab.ps1 (re-run is safe)"
Stop-Transcript | Out-Null
