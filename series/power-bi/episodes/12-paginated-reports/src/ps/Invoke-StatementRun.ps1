#Requires -Version 7.2
<#
.SYNOPSIS
    Exports the store statement of one or more years from the Power BI service, then checks each PDF against the contract.

.DESCRIPTION
    Needs a signed in session (Connect-PowerBIServiceAccount, done by the person running it, never by this script), the workspace id
    and the report id of the uploaded ContosoStoreStatement. -WhatIf prints the requests and sends nothing.
    The contract (contract/store-statement-2025.json) only exists for 2025: other years are exported but not verified.
    Learn: a report that reads a Power BI semantic model needs an identity in the export request -> -Username.

.EXAMPLE
    ./Invoke-StatementRun.ps1 -WorkspaceId $ws -ReportId $rep -Year 2025 -Username alex.demo@contoso.example -OutDir ./out -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string] $WorkspaceId,
    [Parameter(Mandatory)][string] $ReportId,
    [int[]] $Year = 2025,
    [ValidateSet('PDF', 'XLSX', 'DOCX', 'CSV')][string] $Format = 'PDF',
    [string] $Username,
    [string[]] $DatasetId,
    [string] $OutDir = './out',
    [switch] $NoVerify
)
Set-StrictMode -Version Latest
Import-Module (Join-Path $PSScriptRoot 'PbiPaginated' 'PbiPaginated.psd1') -Force

$verify = Join-Path $PSScriptRoot '..' 'tools' 'verify_pdf.py'
$results = foreach ($y in $Year) {
    $file = Join-Path $OutDir ('statement-{0}.{1}' -f $y, $Format.ToLowerInvariant())
    if (-not $WhatIfPreference) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }
    $export = @{ WorkspaceId = $WorkspaceId; ReportId = $ReportId; OutFile = $file; Format = $Format; Parameter = @{ Year = $y }; Username = $Username; DatasetId = $DatasetId }
    $saved = Export-PbiPaginatedReport @export -WhatIf:$WhatIfPreference
    $status = 'whatif'
    if ($saved) {
        $status = 'exported'
        if ($Format -eq 'PDF' -and $y -eq 2025 -and -not $NoVerify) {
            & python3 $verify $saved.FullName | Write-Host
            $status = if ($LASTEXITCODE -eq 0) { 'verified' } else { 'MISMATCH' }
        }
    }
    [pscustomobject]@{ Year = $y; File = $file; Status = $status }
}
$results
if ($results | Where-Object Status -eq 'MISMATCH') { exit 1 }
