<#
.SYNOPSIS
  Creates (or removes) the local Business Central developer container for DEVLADLOG Dynamics 365 episode 12.

.DESCRIPTION
  Runs on the Windows recording laptop, in an elevated Windows PowerShell 5.1 prompt. It
    1. checks that Docker Desktop is installed, running, and in Windows-containers mode (and says how to switch if not),
    2. installs or imports Microsoft's BcContainerHelper module,
    3. asks Get-BcArtifactUrl for the current sandbox artifact (default country us: the CRONUS USA, Inc. demo company),
    4. creates the container 'mglab-bc' with NavUserPassword authentication (New-BcContainer), which also switches on
       the API services (BcContainerHelper sets enableApiServices=Y for Business Central 12 and later), and then proves
       it with one real call to /api/v2.0/companies,
    5. stores the generated admin password DPAPI-encrypted under E:\MGLab\secrets\ (only the same Windows user on this
       machine can decrypt it). The password is never printed and never written inside the repository.

  Idempotent: a running container with its secret is left alone (the API check still runs); a stopped one is started;
  a container without a secret file needs -Recreate, because its password is unknown.
  -Remove tears everything down (container, hosts entry via Remove-BcContainer, and the secret file).

.PARAMETER AcceptEula
  Required to create a container: you accept the Business Central container EULA
  (https://go.microsoft.com/fwlink/?linkid=861843). The script never accepts it for you.

.PARAMETER Isolation
  Optional: process or hyperv, passed to New-BcContainer. Learn: try hyperv if creation fails.

.PARAMETER SetEnv
  Sets BC_BASE_URL, BC_USER and BC_PASSWORD in the current PowerShell process (for 'python -m bckit') and prints nothing
  secret. Run it from the same shell you use for bckit.

.EXAMPLE
  .\New-LabBusinessCentral.ps1 -AcceptEula
.EXAMPLE
  .\New-LabBusinessCentral.ps1 -SetEnv
.EXAMPLE
  .\New-LabBusinessCentral.ps1 -Remove
#>
[CmdletBinding()]
param(
    [string]$ContainerName = 'mglab-bc',
    [string]$Country = 'us',
    [string]$ArtifactVersion = '',
    [string]$MemoryLimit = '8G',
    [string]$AdminUser = 'admin',
    [string]$SecretsFolder = 'E:\MGLab\secrets',
    [ValidateSet('', 'process', 'hyperv')][string]$Isolation = '',
    [switch]$AcceptEula,
    [switch]$Recreate,
    [switch]$Remove,
    [switch]$SetEnv,
    [switch]$AllowPowerShell7
)

$ErrorActionPreference = 'Stop'

# ---- small wrappers (so the tests can replace them) -----------------------------------------------------------

function Get-DockerCommand { Get-Command docker -ErrorAction SilentlyContinue }

function Invoke-Docker {
    param([string[]]$Arguments)
    & docker @Arguments
}

function Test-IsWindowsHost { [Environment]::OSVersion.Platform -eq 'Win32NT' }

function Test-IsAdministrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ---- Docker ---------------------------------------------------------------------------------------------------

function Test-DockerReady {
    <# Returns Ok, Installed, Mode ('windows' | 'linux' | '') and a Message that says what to do next. #>
    if (-not (Get-DockerCommand)) {
        return [pscustomobject]@{ Ok = $false; Installed = $false; Mode = ''; Message =
            'Docker is not installed. Install Docker Desktop (https://www.docker.com/products/docker-desktop/), start it, then switch it to Windows containers.' }
    }
    $mode = ''
    try { $mode = (Invoke-Docker @('info', '--format', '{{.OSType}}') 2>$null | Out-String).Trim() } catch { $mode = '' }
    if ($LASTEXITCODE -ne 0 -or -not $mode) {
        return [pscustomobject]@{ Ok = $false; Installed = $true; Mode = ''; Message =
            'Docker is installed but the engine does not answer. Start Docker Desktop, wait until it says it is running, and run this script again.' }
    }
    if ($mode -ne 'windows') {
        return [pscustomobject]@{ Ok = $false; Installed = $true; Mode = $mode; Message =
            "Docker is in $mode-containers mode, Business Central needs Windows containers. In the taskbar, right-click the Docker icon and choose 'Switch to Windows Containers' (Microsoft Learn, 'Running a container-based development environment'), wait for the engine to restart, then run this script again." }
    }
    [pscustomobject]@{ Ok = $true; Installed = $true; Mode = $mode; Message = 'Docker Desktop is running in Windows-containers mode.' }
}

function Get-LabContainerState {
    <# 'missing' | 'running' | 'stopped' for a container name, from 'docker ps -a'. #>
    param([Parameter(Mandatory)][string]$Name)
    $line = (Invoke-Docker @('ps', '-a', '--filter', "name=^$Name`$", '--format', '{{.Names}}|{{.Status}}') | Out-String).Trim()
    if (-not $line) { return 'missing' }
    if ($line -match '\|Up\b') { 'running' } else { 'stopped' }
}

# ---- secret: generated once, DPAPI-encrypted ------------------------------------------------------------------

function New-LabPassword {
    <# 24 characters from A-Z a-z 0-9 only (nothing that needs quoting in a shell), from a cryptographic generator. #>
    param([int]$Length = 24)
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        do {
            $chars = New-Object System.Collections.Generic.List[char]
            $buf = New-Object byte[] 1
            while ($chars.Count -lt $Length) {
                $rng.GetBytes($buf)
                if ($buf[0] -lt 248) { $chars.Add($alphabet[$buf[0] % 62]) }   # 248 = 4 x 62: no modulo bias
            }
            $pw = -join $chars
        } until ($pw -cmatch '[A-Z]' -and $pw -cmatch '[a-z]' -and $pw -match '[0-9]')
    } finally { $rng.Dispose() }
    $pw
}

function Get-LabSecretPath {
    param([string]$Folder, [string]$Name)
    [System.IO.Path]::Combine($Folder, "$Name.admin.dpapi")
}

function Save-LabSecret {
    <# DPAPI (ConvertFrom-SecureString without -Key): readable only by this Windows user on this machine. #>
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][securestring]$Secret)
    if (-not (Test-IsWindowsHost)) { throw 'DPAPI encryption is only available on Windows; run this script on the recording laptop.' }
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ConvertFrom-SecureString -SecureString $Secret | Set-Content -LiteralPath $Path -Encoding ascii
}

function Read-LabSecret {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    ConvertTo-SecureString -String ((Get-Content -LiteralPath $Path -Raw).Trim())
}

function ConvertTo-PlainInMemory {
    param([Parameter(Mandatory)][securestring]$Secret)
    (New-Object System.Net.NetworkCredential('', $Secret)).Password
}

# ---- BcContainerHelper ----------------------------------------------------------------------------------------

function Initialize-BcContainerHelper {
    if (-not (Get-Module -ListAvailable -Name BcContainerHelper)) {
        Write-Host 'Installing BcContainerHelper from the PowerShell Gallery ...'
        Install-Module BcContainerHelper -Force
    }
    Import-Module BcContainerHelper -DisableNameChecking
}

function Get-LabArtifactUrl {
    param([string]$Country, [string]$Version)
    $p = @{ type = 'Sandbox'; country = $Country; select = 'Latest' }
    if ($Version) { $p.version = $Version }
    $url = Get-BcArtifactUrl @p
    if (-not $url) { throw "Get-BcArtifactUrl returned nothing for sandbox/$Country (version filter '$Version')." }
    $url
}

function Get-LabBaseUrl {
    param([string]$Name)
    "http://${Name}:7048/BC"      # container default: HTTP, OData/API port 7048, server instance BC
}

function Invoke-LabApi {
    <# One GET against the container API with basic authentication; the password only lives in memory. #>
    param([string]$BaseUrl, [string]$User, [securestring]$Secret, [string]$Path = 'companies')
    $pair = '{0}:{1}' -f $User, (ConvertTo-PlainInMemory $Secret)
    $h = @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair)); Accept = 'application/json' }
    Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v2.0/$Path" -Headers $h -TimeoutSec 30
}

function Wait-LabApi {
    <# Proves the API is on: /api/v2.0/companies answers. Retries while the service tier is still starting. #>
    param([string]$BaseUrl, [string]$User, [securestring]$Secret, [int]$TimeoutSec = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $last = $null
    do {
        try {
            $r = Invoke-LabApi -BaseUrl $BaseUrl -User $User -Secret $Secret
            return @($r.value)
        } catch {
            $last = $_.Exception.Message
            $code = $null
            if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
            if ($code -eq 401) {
                throw "The API answered 401. Learn (Web services authentication): on-premises basic authentication takes the web service access key as password; sign in to the web client as $User, open the user card and create one, or re-create the container with -Recreate."
            }
            if ($code -eq 405) {
                throw "The API answered 405: OData or API services are off on the server instance. Learn, 'Enabling the APIs for Business Central': Set-NAVServerConfiguration with ODataServicesEnabled and ApiServicesEnabled set to true."
            }
            Start-Sleep -Seconds 5
        }
    } while ((Get-Date) -lt $deadline)
    throw "The API at $BaseUrl did not answer within $TimeoutSec s. Last error: $last"
}

# ---- actions --------------------------------------------------------------------------------------------------

function Assert-Prerequisites {
    param([switch]$AllowPowerShell7)
    if (-not (Test-IsWindowsHost)) { throw 'This script creates a Windows container: run it on the Windows recording laptop.' }
    if (-not (Test-IsAdministrator)) { throw 'Run this script in an elevated (Run as administrator) PowerShell window: New-BcContainer needs it.' }
    if ($PSVersionTable.PSEdition -eq 'Core' -and -not $AllowPowerShell7) {
        throw "Use Windows PowerShell 5.1 (powershell.exe). Learn: for 2026 release wave 1 (version 28.0) containers, PowerShell 7 has a known issue loading the Business Central admin modules; pass -AllowPowerShell7 to try anyway."
    }
    $d = Test-DockerReady
    if (-not $d.Ok) { throw $d.Message }
    Write-Host $d.Message
}

function Invoke-LabRemove {
    param([string]$Name, [string]$SecretPath)
    Initialize-BcContainerHelper
    if ((Get-LabContainerState -Name $Name) -ne 'missing') {
        Write-Host "Removing container $Name (container, hosts entry, shortcuts) ..."
        Remove-BcContainer -containerName $Name
    } else {
        Write-Host "Container $Name does not exist."
    }
    if (Test-Path -LiteralPath $SecretPath) {
        Remove-Item -LiteralPath $SecretPath -Force
        Write-Host 'Removed the encrypted admin password file.'
    }
    Write-Host "Done. The artifact cache (C:\bcartifacts.cache) and the Docker image layers stay for the next run; delete them by hand to free about 15 GB."
}

function Invoke-LabCreate {
    param([string]$Name, [string]$Country, [string]$Version, [string]$Memory, [string]$User, [string]$SecretPath, [string]$Isolation = '', [switch]$AcceptEula)
    if (-not $AcceptEula) {
        throw 'Creating the container needs -AcceptEula (you accept the Business Central container EULA: https://go.microsoft.com/fwlink/?linkid=861843).'
    }
    Initialize-BcContainerHelper
    $artifactUrl = Get-LabArtifactUrl -Country $Country -Version $Version
    Write-Host "Artifact: $artifactUrl"

    $plain = New-LabPassword
    $secure = ConvertTo-SecureString -String $plain -AsPlainText -Force
    Remove-Variable plain
    # saved first: a failed create never leaves a container with an unknown password
    Save-LabSecret -Path $SecretPath -Secret $secure
    $credential = New-Object System.Management.Automation.PSCredential($User, $secure)

    Write-Host "Creating container $Name (memory limit $Memory). The first run downloads about 15 GB and takes a while ..."
    # -isolation hyperv is Learn's first suggestion when creation fails with process isolation
    $extra = @{}
    if ($Isolation) { $extra.isolation = $Isolation }
    New-BcContainer -accept_eula -containerName $Name -artifactUrl $artifactUrl `
        -auth NavUserPassword -Credential $credential `
        -memoryLimit $Memory -updateHosts -assignPremiumPlan -shortcuts None @extra | Out-Null
    return $secure
}

function Invoke-LabMain {
    [CmdletBinding()]
    param(
        [string]$ContainerName = 'mglab-bc',
        [string]$Country = 'us',
        [string]$ArtifactVersion = '',
        [string]$MemoryLimit = '8G',
        [string]$AdminUser = 'admin',
        [string]$SecretsFolder = 'E:\MGLab\secrets',
        [string]$Isolation = '',
        [switch]$AcceptEula,
        [switch]$Recreate,
        [switch]$Remove,
        [switch]$SetEnv,
        [switch]$AllowPowerShell7
    )
    $secretPath = Get-LabSecretPath -Folder $SecretsFolder -Name $ContainerName
    $baseUrl = Get-LabBaseUrl -Name $ContainerName

    if ($Remove) {
        if (-not (Test-IsAdministrator)) { throw 'Run this script in an elevated PowerShell window.' }
        Invoke-LabRemove -Name $ContainerName -SecretPath $secretPath
        return
    }

    if ($SetEnv) {
        $secure = Read-LabSecret -Path $secretPath
        if (-not $secure) { throw "No secret at ${secretPath}: create the container first." }
        $env:BC_BASE_URL = $baseUrl
        $env:BC_USER = $AdminUser
        $env:BC_PASSWORD = ConvertTo-PlainInMemory $secure
        Write-Host "BC_BASE_URL, BC_USER and BC_PASSWORD are set for this PowerShell session (password not shown)."
        return
    }

    Assert-Prerequisites -AllowPowerShell7:$AllowPowerShell7
    $state = Get-LabContainerState -Name $ContainerName
    $secure = Read-LabSecret -Path $secretPath

    if ($Recreate -and $state -ne 'missing') {
        Invoke-LabRemove -Name $ContainerName -SecretPath $secretPath
        $state = 'missing'; $secure = $null
    }

    switch ($state) {
        'running' { Write-Host "Container $ContainerName is already running." }
        'stopped' { Write-Host "Starting container $ContainerName ..."; Invoke-Docker @('start', $ContainerName) | Out-Null }
        'missing' {
            $secure = Invoke-LabCreate -Name $ContainerName -Country $Country -Version $ArtifactVersion -Memory $MemoryLimit `
                -User $AdminUser -SecretPath $secretPath -Isolation $Isolation -AcceptEula:$AcceptEula
        }
    }
    if (-not $secure) {
        throw "Container $ContainerName exists but there is no secret at $secretPath, so its admin password is unknown. Run again with -Recreate."
    }

    $companies = Wait-LabApi -BaseUrl $baseUrl -User $AdminUser -Secret $secure
    Write-Host ("API ok at $baseUrl/api/v2.0 : {0} company(ies): {1}" -f $companies.Count, (($companies | ForEach-Object { $_.name }) -join ', '))
    Write-Host "Web client: the URL printed in the container log above   user: $AdminUser   password: stored DPAPI-encrypted in $secretPath"
    Write-Host "Next: .\New-LabBusinessCentral.ps1 -SetEnv   then   python -m bckit doctor"
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-LabMain -ContainerName $ContainerName -Country $Country -ArtifactVersion $ArtifactVersion -MemoryLimit $MemoryLimit `
        -AdminUser $AdminUser -SecretsFolder $SecretsFolder -Isolation $Isolation -AcceptEula:$AcceptEula -Recreate:$Recreate -Remove:$Remove `
        -SetEnv:$SetEnv -AllowPowerShell7:$AllowPowerShell7
}
