#Requires -Version 7.2
<#
.SYNOPSIS
    Paginated reports (.rdl) through the Power BI REST API: upload, export, wait, download.

.DESCRIPTION
    New-PbiMultipartFile       writes the multipart/form-data body of an .rdl upload to a file (Invoke-PowerBIRestMethod -InFile)
    Import-PbiRdl              Imports - Post Import In Group for an .rdl (name conflict Abort or Overwrite only), waits for the import
    Wait-PbiImport             polls Get Import In Group until Succeeded or Failed
    Start-PbiExport            Reports - Export To File In Group for a paginated report: format, parameter values, identity
    Wait-PbiExport             polls Get Export To File Status In Group until Succeeded or Failed
    Save-PbiExport             Get File Of Export To File In Group, written to a file
    Export-PbiPaginatedReport  start, wait and save in one call

    All REST calls go through Invoke-PowerBIRestMethod (module MicrosoftPowerBIMgmt, after Connect-PowerBIServiceAccount).
    Every function that sends something supports -WhatIf. Nothing here signs in.
#>

Set-StrictMode -Version Latest

# Formats Learn lists for paginated reports in the FileFormat enumeration of Export To File (PNG is for Power BI reports only).
$script:PaginatedFormats = 'PDF', 'ACCESSIBLEPDF', 'XLSX', 'DOCX', 'PPTX', 'CSV', 'XML', 'MHTML', 'IMAGE'

function Invoke-PbiApi {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][ValidateSet('Get', 'Post')][string] $Method,
        [Parameter(Mandatory)][string] $Url,
        [hashtable] $Body,
        [string] $InFile,
        [string] $ContentType,
        [string] $OutFile
    )
    $params = @{ Method = $Method; Url = $Url }
    if ($Body) { $params.Body = $Body | ConvertTo-Json -Depth 8 -Compress }
    if ($InFile) { $params.InFile = $InFile; $params.ContentType = $ContentType }
    if ($OutFile) { $params.OutFile = $OutFile; return Invoke-PowerBIRestMethod @params }
    $json = Invoke-PowerBIRestMethod @params
    if ([string]::IsNullOrWhiteSpace($json)) { return $null }
    $json | ConvertFrom-Json
}

function New-PbiMultipartFile {
    <#
    .SYNOPSIS  Writes a multipart/form-data body with one file part. Returns the body path and the Content-Type (with the boundary).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $Path,
        [Parameter(Mandatory)][string] $OutFile,
        [string] $Boundary = ('mglab' + [guid]::NewGuid().ToString('N'))
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "File not found: $Path" }
    $name = [IO.Path]::GetFileName($Path)
    $head = [Text.Encoding]::UTF8.GetBytes("--$Boundary`r`nContent-Disposition: form-data; name=`"file0`"; filename=`"$name`"`r`nContent-Type: application/octet-stream`r`n`r`n")
    $tail = [Text.Encoding]::UTF8.GetBytes("`r`n--$Boundary--`r`n")
    $content = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Path))
    $stream = [IO.File]::Create($OutFile)
    try { $stream.Write($head); $stream.Write($content); $stream.Write($tail) } finally { $stream.Dispose() }
    [pscustomobject]@{ Path = $OutFile; ContentType = "multipart/form-data; boundary=$Boundary"; Boundary = $Boundary }
}

function Wait-PbiImport {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $ImportId,
        [int] $TimeoutSeconds = 300,
        [int] $IntervalSeconds = 5
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $import = Invoke-PbiApi -Method Get -Url "groups/$WorkspaceId/imports/$ImportId"
        if ($import.importState -eq 'Succeeded') { return $import }
        if ($import.importState -eq 'Failed') {
            $why = if ($import.PSObject.Properties['error'] -and $import.error) { $import.error.code } else { 'no error details' }
            throw "Import $ImportId failed: $why"
        }
        if ($IntervalSeconds -gt 0) { Start-Sleep -Seconds $IntervalSeconds }
    } while ((Get-Date) -lt $deadline)
    throw "Import $ImportId did not finish within $TimeoutSeconds seconds (last state: $($import.importState))"
}

function Import-PbiRdl {
    <#
    .SYNOPSIS  Uploads an .rdl to a workspace. Learn: datasetDisplayName is the file name WITH the .rdl extension; for .rdl use Abort or Overwrite.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $Path,
        [string] $Name,
        [ValidateSet('Abort', 'Overwrite')][string] $NameConflict = 'Abort',
        [int] $IntervalSeconds = 5
    )
    if ([IO.Path]::GetExtension($Path) -ne '.rdl') { throw "Not an .rdl file: $Path" }
    if (-not $Name) { $Name = [IO.Path]::GetFileName($Path) }
    if (-not $Name.EndsWith('.rdl')) { $Name += '.rdl' }
    $url = 'groups/{0}/imports?datasetDisplayName={1}&nameConflict={2}' -f $WorkspaceId, [uri]::EscapeDataString($Name), $NameConflict
    if (-not $PSCmdlet.ShouldProcess("workspace $WorkspaceId", "POST $url")) { return [pscustomobject]@{ Url = $url; Sent = $false } }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("rdl-upload-" + [guid]::NewGuid().ToString('N') + '.bin')
    try {
        $body = New-PbiMultipartFile -Path $Path -OutFile $tmp
        $started = Invoke-PbiApi -Method Post -Url $url -InFile $body.Path -ContentType $body.ContentType
    } finally { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
    Wait-PbiImport -WorkspaceId $WorkspaceId -ImportId $started.id -IntervalSeconds $IntervalSeconds
}

function New-PbiExportRequest {
    <#
    .SYNOPSIS  The body of Export To File for a paginated report. Parameter values are strings (Learn: ParameterValue name, value).
    #>
    [CmdletBinding()]
    param(
        [ValidateSet('PDF', 'ACCESSIBLEPDF', 'XLSX', 'DOCX', 'PPTX', 'CSV', 'XML', 'MHTML', 'IMAGE')][string] $Format = 'PDF',
        [hashtable] $Parameter,
        [string] $Username,
        [string[]] $DatasetId,
        [string] $Locale
    )
    $config = [ordered]@{}
    if ($Parameter -and $Parameter.Count) {
        $config.parameterValues = @($Parameter.GetEnumerator() | Sort-Object Name | ForEach-Object { [ordered]@{ name = [string]$_.Name; value = [string]$_.Value } })
    }
    if ($Username) {
        $identity = [ordered]@{ username = $Username }
        if ($DatasetId) { $identity.datasets = @($DatasetId) }
        $config.identities = @($identity)
    }
    if ($Locale) { $config.locale = $Locale }
    $body = [ordered]@{ format = $Format }
    if ($config.Count) { $body.paginatedReportConfiguration = $config }
    $body
}

function Start-PbiExport {
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Low')]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $ReportId,
        [ValidateSet('PDF', 'ACCESSIBLEPDF', 'XLSX', 'DOCX', 'PPTX', 'CSV', 'XML', 'MHTML', 'IMAGE')][string] $Format = 'PDF',
        [hashtable] $Parameter,
        [string] $Username,
        [string[]] $DatasetId,
        [string] $Locale
    )
    $request = New-PbiExportRequest -Format $Format -Parameter $Parameter -Username $Username -DatasetId $DatasetId -Locale $Locale
    $url = "groups/$WorkspaceId/reports/$ReportId/ExportTo"
    if (-not $PSCmdlet.ShouldProcess($url, "POST $($request | ConvertTo-Json -Depth 8 -Compress)")) { return $null }
    Invoke-PbiApi -Method Post -Url $url -Body ([hashtable]$request)
}

function Wait-PbiExport {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $ReportId,
        [Parameter(Mandatory)][string] $ExportId,
        [int] $TimeoutSeconds = 600,
        [int] $IntervalSeconds = 5
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $export = Invoke-PbiApi -Method Get -Url "groups/$WorkspaceId/reports/$ReportId/exports/$ExportId"
        if ($export.status -eq 'Succeeded') { return $export }
        if ($export.status -eq 'Failed') { throw "Export $ExportId failed" }
        if ($IntervalSeconds -gt 0) { Start-Sleep -Seconds $IntervalSeconds }
    } while ((Get-Date) -lt $deadline)
    throw "Export $ExportId did not finish within $TimeoutSeconds seconds (last status: $($export.status), $($export.percentComplete) %)"
}

function Save-PbiExport {
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $ReportId,
        [Parameter(Mandatory)][string] $ExportId,
        [Parameter(Mandatory)][string] $OutFile
    )
    $url = "groups/$WorkspaceId/reports/$ReportId/exports/$ExportId/file"
    if ($PSCmdlet.ShouldProcess($OutFile, "GET $url")) {
        Invoke-PbiApi -Method Get -Url $url -OutFile $OutFile | Out-Null
        Get-Item -LiteralPath $OutFile
    }
}

function Export-PbiPaginatedReport {
    <#
    .SYNOPSIS  Start, wait, save. Returns the file. With -WhatIf only the request is shown.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $ReportId,
        [Parameter(Mandatory)][string] $OutFile,
        [ValidateSet('PDF', 'ACCESSIBLEPDF', 'XLSX', 'DOCX', 'PPTX', 'CSV', 'XML', 'MHTML', 'IMAGE')][string] $Format = 'PDF',
        [hashtable] $Parameter,
        [string] $Username,
        [string[]] $DatasetId,
        [string] $Locale,
        [int] $IntervalSeconds = 5,
        [int] $TimeoutSeconds = 600
    )
    $start = @{ WorkspaceId = $WorkspaceId; ReportId = $ReportId; Format = $Format; Parameter = $Parameter; Username = $Username; DatasetId = $DatasetId; Locale = $Locale }
    $job = Start-PbiExport @start -WhatIf:$WhatIfPreference
    if (-not $job) { return $null }
    $done = Wait-PbiExport -WorkspaceId $WorkspaceId -ReportId $ReportId -ExportId $job.id -IntervalSeconds $IntervalSeconds -TimeoutSeconds $TimeoutSeconds
    Save-PbiExport -WorkspaceId $WorkspaceId -ReportId $ReportId -ExportId $done.id -OutFile $OutFile
}

Export-ModuleMember -Function New-PbiMultipartFile, Import-PbiRdl, Wait-PbiImport, New-PbiExportRequest, Start-PbiExport, Wait-PbiExport, Save-PbiExport, Export-PbiPaginatedReport
