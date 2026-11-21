<#
.SYNOPSIS
  Gate for an unpacked Power Platform solution folder before it is packed or committed.

.DESCRIPTION
  Reads the folder that `pac solution unpack --packagetype Both` writes (Other/Solution.xml,
  Other/Customizations.xml, environmentvariabledefinitions/...) and fails on the mistakes that
  only show up later, in the TEST or PROD import:

    S01  Solution.xml and Customizations.xml exist and are well-formed XML
    S02  the solution unique name is the expected one
    S03  the version is four numeric parts (major.minor.build.revision)
    S04  <Managed> is 2 (source unpacked as Both), otherwise `pac solution pack --packagetype Managed` fails
    S05  the publisher prefix is the expected one
    S06  every environment variable listed as a root component (type 380) has a folder
    S07  environment variable names use the publisher prefix and match their folder; default value <= 2000 chars
    S08  no file with current values of environment variables (they belong to the target, not to source)
    S09  a Secret environment variable has no default value
    S10  connection references use the prefix, a /providers/Microsoft.PowerApps/apis/ connector id
         and carry no connection id
    S11  no environment URL (*.crm*.dynamics.com) or tenant name (*.onmicrosoft.com) in any text file

  Prints one line per finding and exits 1 when anything failed, 0 otherwise.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Path,
    [string] $ExpectedName = 'EquipmentDesk',
    [string] $ExpectedPrefix = 'contoso'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$findings = [System.Collections.Generic.List[string]]::new()
function Add-Finding([string] $Id, [string] $Message) {
    $findings.Add("FAIL $Id $Message")
}

function Read-Xml([string] $File) {
    $doc = [xml]::new()
    $doc.PreserveWhitespace = $false
    $doc.Load($File)
    return $doc
}

$solutionFile = Join-Path $Path 'Other/Solution.xml'
$customFile = Join-Path $Path 'Other/Customizations.xml'

# S01
$solution = $null
$custom = $null
foreach ($f in @($solutionFile, $customFile)) {
    if (-not (Test-Path -LiteralPath $f)) { Add-Finding 'S01' "missing file $f"; continue }
    try {
        $doc = Read-Xml $f
        if ($f -eq $solutionFile) { $solution = $doc } else { $custom = $doc }
    }
    catch { Add-Finding 'S01' "$f is not well-formed XML: $($_.Exception.Message)" }
}

$envDefinitionFolders = @()
$envRoot = Join-Path $Path 'environmentvariabledefinitions'
if (Test-Path -LiteralPath $envRoot) {
    $envDefinitionFolders = @(Get-ChildItem -LiteralPath $envRoot -Directory | ForEach-Object Name)
}

if ($solution) {
    $manifest = $solution.ImportExportXml.SolutionManifest

    # S02
    if ($manifest.UniqueName -ne $ExpectedName) {
        Add-Finding 'S02' "solution unique name is '$($manifest.UniqueName)', expected '$ExpectedName'"
    }
    # S03
    if ($manifest.Version -notmatch '^\d+\.\d+\.\d+\.\d+$') {
        Add-Finding 'S03' "version '$($manifest.Version)' is not major.minor.build.revision"
    }
    # S04
    if ("$($manifest.Managed)" -ne '2') {
        Add-Finding 'S04' "<Managed> is '$($manifest.Managed)', expected 2 (unpack with --packagetype Both so a managed zip can be packed)"
    }
    # S05
    if ($manifest.Publisher.CustomizationPrefix -ne $ExpectedPrefix) {
        Add-Finding 'S05' "publisher prefix is '$($manifest.Publisher.CustomizationPrefix)', expected '$ExpectedPrefix'"
    }
    # S06 (environment variable definitions are component type 380)
    $rootEnv = @()
    if ($manifest.RootComponents -and $manifest.RootComponents.PSObject.Properties['RootComponent']) {
        $rootEnv = @($manifest.RootComponents.RootComponent | Where-Object { $_.type -eq '380' } | ForEach-Object schemaName)
    }
    foreach ($name in $rootEnv) {
        if ($name -notin $envDefinitionFolders) { Add-Finding 'S06' "root component $name has no folder under environmentvariabledefinitions" }
    }
}

# S07, S09
foreach ($name in $envDefinitionFolders) {
    $file = Join-Path $envRoot "$name/environmentvariabledefinition.xml"
    if (-not (Test-Path -LiteralPath $file)) { Add-Finding 'S07' "$name has no environmentvariabledefinition.xml"; continue }
    try { $def = (Read-Xml $file).environmentvariabledefinition }
    catch { Add-Finding 'S07' "$file is not an environment variable definition (unreadable or wrong root element)"; continue }
    if ($def.schemaname -ne $name) { Add-Finding 'S07' "folder $name holds schemaname '$($def.schemaname)'" }
    if (-not $def.schemaname.StartsWith("${ExpectedPrefix}_")) { Add-Finding 'S07' "$($def.schemaname) does not start with ${ExpectedPrefix}_" }
    if ($def.schemaname.Length -gt 100) { Add-Finding 'S07' "$($def.schemaname) is longer than 100 characters" }
    $default = if ($def.PSObject.Properties['defaultvalue']) { [string] $def.defaultvalue } else { '' }
    if ($default.Length -gt 2000) { Add-Finding 'S07' "$($def.schemaname) default value is longer than 2000 characters" }
    $type = if ($def.PSObject.Properties['type']) { [string] $def.type } else { '' }
    if ($type -eq '100000005' -and $default) { Add-Finding 'S09' "$($def.schemaname) is a Secret and has a default value" }
}

# S08
if (Test-Path -LiteralPath $Path) {
    Get-ChildItem -LiteralPath $Path -Recurse -File | Where-Object { $_.Name -like '*environmentvariablevalue*' } | ForEach-Object {
        Add-Finding 'S08' "current environment variable values are committed: $($_.FullName.Substring($Path.Length).TrimStart('/\'))"
    }
}

# S10
if ($custom) {
    $refs = @()
    if ($custom.ImportExportXml.PSObject.Properties['connectionreferences'] -and $custom.ImportExportXml.connectionreferences) {
        $node = $custom.ImportExportXml.connectionreferences
        if ($node -isnot [string] -and $node.PSObject.Properties['connectionreference']) { $refs = @($node.connectionreference) }
    }
    foreach ($ref in $refs) {
        $logical = $ref.connectionreferencelogicalname
        if (-not $logical.StartsWith("${ExpectedPrefix}_")) { Add-Finding 'S10' "connection reference $logical does not start with ${ExpectedPrefix}_" }
        if ($ref.connectorid -notlike '/providers/Microsoft.PowerApps/apis/*') { Add-Finding 'S10' "connection reference $logical has connector id '$($ref.connectorid)'" }
        if ($ref.PSObject.Properties['connectionid']) { Add-Finding 'S10' "connection reference $logical carries a connection id" }
    }
}

# S11
$secretPatterns = @(
    @{ Id = 'environment URL'; Regex = '[A-Za-z0-9-]+\.crm\d*\.dynamics\.com' },
    @{ Id = 'tenant name'; Regex = '[A-Za-z0-9-]+\.onmicrosoft\.com' }
)
if (Test-Path -LiteralPath $Path) {
    Get-ChildItem -LiteralPath $Path -Recurse -File | Where-Object { $_.Extension -in '.xml', '.json', '.yaml', '.yml', '.txt', '.resx' } | ForEach-Object {
        $text = Get-Content -LiteralPath $_.FullName -Raw
        foreach ($p in $secretPatterns) {
            if ($text -match $p.Regex) {
                Add-Finding 'S11' "$($p.Id) found in $($_.FullName.Substring($Path.Length).TrimStart('/\'))"
            }
        }
    }
}

if ($findings.Count -eq 0) {
    Write-Output "OK  $ExpectedName source at $Path passed all checks (S01-S11)"
    exit 0
}
$findings | ForEach-Object { Write-Output $_ }
exit 1
