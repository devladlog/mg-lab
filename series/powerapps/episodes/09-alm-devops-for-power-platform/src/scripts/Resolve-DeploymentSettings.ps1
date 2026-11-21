<#
.SYNOPSIS
  Turns a deployment settings template from source control into the file the import task reads.

.DESCRIPTION
  Templates (src/settings/*.settings.json) use the format of Learn's "deployment settings file"
  (EnvironmentVariables / ConnectionReferences). Values that are configuration (a domain) are written in
  the template. Values that are identifiers of the target (connection ids) are tokens like
  ${TEST_CONNECTION_OUTLOOK}, filled from process environment variables, which an Azure DevOps variable
  group provides, so they never reach git.

  Checks, in this order, and exits 1 on the first group of problems:
    - every token has an environment variable (the missing names are listed; values are never printed)
    - the template covers exactly the environment variables and connection references of the solution
      folder: nothing missing, nothing unknown, each connector id equals the solution's
    - after resolution every Value / ConnectionId is a non-empty string
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Template,
    [Parameter(Mandatory)] [string] $Output,
    [Parameter(Mandatory)] [string] $SolutionPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Fail([string[]] $Messages) {
    $Messages | ForEach-Object { Write-Output "FAIL $_" }
    exit 1
}

$text = Get-Content -LiteralPath $Template -Raw
$tokens = [regex]::Matches($text, '\$\{([A-Za-z0-9_]+)\}') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
$missing = @($tokens | Where-Object { [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($_)) })
if ($missing.Count -gt 0) {
    Fail @("no value for: $($missing -join ', ') (set them in the pipeline's variable group)")
}
foreach ($t in $tokens) {
    $text = $text.Replace('${' + $t + '}', [Environment]::GetEnvironmentVariable($t))
}

try { $settings = $text | ConvertFrom-Json } catch { Fail @("$Template is not valid JSON after resolving tokens: $($_.Exception.Message)") }

# what the solution defines
$definedEnv = @()
$envRoot = Join-Path $SolutionPath 'environmentvariabledefinitions'
if (Test-Path -LiteralPath $envRoot) { $definedEnv = @(Get-ChildItem -LiteralPath $envRoot -Directory | ForEach-Object Name) }
$definedRefs = @{}
$custom = [xml](Get-Content -LiteralPath (Join-Path $SolutionPath 'Other/Customizations.xml') -Raw)
$node = $custom.ImportExportXml.connectionreferences
if ($node -and $node -isnot [string] -and $node.PSObject.Properties['connectionreference']) {
    foreach ($r in @($node.connectionreference)) { $definedRefs[$r.connectionreferencelogicalname] = $r.connectorid }
}

$problems = [System.Collections.Generic.List[string]]::new()
$envSettings = @($settings.EnvironmentVariables)
$refSettings = @($settings.ConnectionReferences)

foreach ($n in $definedEnv) { if ($n -notin @($envSettings | ForEach-Object SchemaName)) { $problems.Add("environment variable $n has no entry in $(Split-Path $Template -Leaf)") } }
foreach ($e in $envSettings) {
    if ($e.SchemaName -notin $definedEnv) { $problems.Add("$($e.SchemaName) is in the settings but not in the solution") }
    if ($e.Value -isnot [string] -or [string]::IsNullOrWhiteSpace($e.Value)) { $problems.Add("environment variable $($e.SchemaName) has an empty value") }
}
foreach ($n in $definedRefs.Keys) { if ($n -notin @($refSettings | ForEach-Object LogicalName)) { $problems.Add("connection reference $n has no entry in $(Split-Path $Template -Leaf)") } }
foreach ($r in $refSettings) {
    if (-not $definedRefs.ContainsKey($r.LogicalName)) { $problems.Add("$($r.LogicalName) is in the settings but not in the solution"); continue }
    if ($r.ConnectorId -ne $definedRefs[$r.LogicalName]) { $problems.Add("connection reference $($r.LogicalName): connector id differs from the solution's") }
    if ($r.ConnectionId -isnot [string] -or [string]::IsNullOrWhiteSpace($r.ConnectionId)) { $problems.Add("connection reference $($r.LogicalName) has an empty connection id") }
}
if ($problems.Count -gt 0) { Fail $problems }

# write only the documented keys
$clean = [ordered]@{
    EnvironmentVariables = @($envSettings | ForEach-Object { [ordered]@{ SchemaName = $_.SchemaName; Value = $_.Value } })
    ConnectionReferences = @($refSettings | ForEach-Object { [ordered]@{ LogicalName = $_.LogicalName; ConnectionId = $_.ConnectionId; ConnectorId = $_.ConnectorId } })
}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent ([System.IO.Path]::GetFullPath($Output))) | Out-Null
$clean | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding utf8
Write-Output ("OK  {0}: {1} environment variable(s), {2} connection reference(s), {3} token(s) filled ({4})" -f (Split-Path $Template -Leaf), $envSettings.Count, $refSettings.Count, $tokens.Count, ($tokens -join ', '))
