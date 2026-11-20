#Requires -Version 7.2
<#
  MG Lab #6 — file share → SharePoint migration helpers (PnP.PowerShell 3.x).
  Pure functions (mapping, pre-flight) are unit-tested with Pester; the PnP functions are idempotent: safe to re-run.
#>

# Legacy top-level folders → the Department values used in SharePoint (episode 3 choices)
$script:DepartmentMap = @{
    'Accounts'          = 'Finance'
    'People'            = 'HR'
    'Ops'               = 'Operations'
    'Sales & Marketing' = 'Sales'
    'IT Support'        = 'IT'
}
$script:DocTypeMap = @{
    '.docx' = 'Document'; '.doc' = 'Document'; '.pdf' = 'Document'; '.txt' = 'Document'
    '.xlsx' = 'Spreadsheet'; '.xls' = 'Spreadsheet'; '.csv' = 'Spreadsheet'
    '.pptx' = 'Presentation'; '.ppt' = 'Presentation'
}
$script:InvalidChars   = '["*:<>?/\\|]'
$script:BlockedNames   = '^(~\$.*|Thumbs\.db|desktop\.ini|\.DS_Store)$|\.tmp$'
$script:MaxUrlLength   = 400        # SharePoint limit for the full decoded path
$script:MaxFileBytes   = 250GB

function Get-MgDepartment {
    [CmdletBinding()] param([Parameter(Mandatory)][string] $RelativePath)
    $top = ($RelativePath -split '[\\/]')[0]
    if ($script:DepartmentMap.ContainsKey($top)) { $script:DepartmentMap[$top] } else { $null }
}

function Get-MgDocType {
    [CmdletBinding()] param([Parameter(Mandatory)][string] $Name)
    $ext = [IO.Path]::GetExtension($Name).ToLowerInvariant()
    if ($script:DocTypeMap.ContainsKey($ext)) { $script:DocTypeMap[$ext] } else { 'Other' }
}

function Test-MgMigrationItem {
    <# Returns the list of blocking issues for one file. Empty = ready to migrate. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $RelativePath,
        [Parameter(Mandatory)][long]   $SizeBytes,
        [Parameter(Mandatory)][string] $TargetLibraryUrl     # e.g. /sites/MGLabDemo/Migrated Documents
    )
    $name   = Split-Path $RelativePath -Leaf
    $issues = [Collections.Generic.List[string]]::new()
    if ($name -match $script:BlockedNames)          { $issues.Add('BlockedFile') }
    if ($name -match $script:InvalidChars)          { $issues.Add('InvalidCharacters') }
    if ($name -match '^\s|\s$|\.$')                 { $issues.Add('LeadingOrTrailingSpaceOrDot') }
    if ($SizeBytes -eq 0)                           { $issues.Add('EmptyFile') }
    if ($SizeBytes -gt $script:MaxFileBytes)        { $issues.Add('TooLarge') }
    if (-not (Get-MgDepartment $RelativePath))      { $issues.Add('UnmappedFolder') }
    $target = "$TargetLibraryUrl/$((Get-MgDepartment $RelativePath) ?? 'Unmapped')/$name"
    if ($target.Length -gt $script:MaxUrlLength)    { $issues.Add('PathTooLong') }
    $issues.ToArray()   # empty array = ready
}

function Get-MgMigrationInventory {
    <# Scans the source folder and returns one row per file, with mapping and pre-flight issues. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $SourcePath, [Parameter(Mandatory)][string] $TargetLibraryUrl)
    $root = (Resolve-Path $SourcePath).Path.TrimEnd('/', '\')
    Get-ChildItem -Path $root -File -Recurse -Force | ForEach-Object {
        $rel    = $_.FullName.Substring($root.Length + 1)
        $issues = Test-MgMigrationItem -RelativePath $rel -SizeBytes $_.Length -TargetLibraryUrl $TargetLibraryUrl
        [pscustomobject]@{
            RelativePath = $rel
            Name         = $_.Name
            SizeKB       = [math]::Round($_.Length / 1KB, 1)
            Modified     = $_.LastWriteTimeUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
            Department   = Get-MgDepartment $rel
            DocType      = Get-MgDocType $_.Name
            Issues       = $issues -join ';'
            Ready        = @($issues).Count -eq 0
        }
    }
}

function Initialize-MgMigrationTarget {
    <# Creates the document library and its columns if they don't exist yet (idempotent). #>
    [CmdletBinding()] param([string] $Library = 'Migrated Documents')
    if (-not (Get-PnPList -Identity $Library -ErrorAction SilentlyContinue)) {
        New-PnPList -Title $Library -Url ($Library -replace '\s', '') -Template DocumentLibrary -EnableVersioning -OnQuickLaunch | Out-Null
        Write-Host "Created library '$Library'"
    }
    $fields = @(
        @{ Name = 'Department';   Type = 'Choice'; Choices = 'Finance', 'HR', 'Operations', 'Sales', 'IT' }
        @{ Name = 'DocType';      Type = 'Choice'; Choices = 'Document', 'Spreadsheet', 'Presentation', 'Other' }
        @{ Name = 'LegacyPath';   Type = 'Note' }     # multi-line: single line of text stops at 255 characters
    )
    foreach ($f in $fields) {
        $existing = Get-PnPField -List $Library -Identity $f.Name -ErrorAction SilentlyContinue
        if ($existing -and $existing.TypeAsString -ne $f.Type -and $f.Type -eq 'Note' -and $existing.TypeAsString -eq 'Text') {
            Set-PnPField -List $Library -Identity $f.Name -Values @{ TypeAsString = 'Note' } | Out-Null   # keeps the values
            Write-Host "Changed column '$($f.Name)' to multi-line text"
        }
        if (-not $existing) {
            $p = @{ List = $Library; DisplayName = $f.Name; InternalName = $f.Name; Type = $f.Type; AddToDefaultView = $true }
            if ($f.Choices) { $p.Choices = $f.Choices }
            Add-PnPField @p | Out-Null
            Write-Host "Added column '$($f.Name)'"
        }
    }
}

function Invoke-MgMigration {
    <# Copies every Ready file, sets metadata and the original Modified date, and logs each result. Re-runnable. #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]   $SourcePath,
        [Parameter(Mandatory)][object[]] $Inventory,
        [string] $Library = 'Migrated Documents',
        [string] $LogPath = './migration-log.csv'
    )
    $list    = Get-PnPList -Identity $Library -Includes RootFolder.ServerRelativeUrl
    $libUrl  = $list.RootFolder.ServerRelativeUrl                          # /sites/x/MigratedDocuments
    $webUrl  = (Get-PnPWeb).ServerRelativeUrl.TrimEnd('/')
    $libSite = $libUrl.Substring($webUrl.Length).TrimStart('/')           # MigratedDocuments
    $log = foreach ($row in $Inventory) {
        if (-not $row.Ready) {
            [pscustomobject]@{ RelativePath = $row.RelativePath; Status = 'Skipped'; Detail = $row.Issues; Url = '' }
            continue
        }
        $folder = "$libSite/$($row.Department)"                            # site-relative
        $url    = "$libUrl/$($row.Department)/$($row.Name)"
        try {
            $existing = $null
            try { $existing = Get-PnPFile -Url $url -AsListItem -ErrorAction Stop } catch { }   # not there yet
            if ($existing -and $existing['LegacyPath'] -eq $row.RelativePath) {
                [pscustomobject]@{ RelativePath = $row.RelativePath; Status = 'AlreadyMigrated'; Detail = ''; Url = $url }
                continue
            }
            if ($PSCmdlet.ShouldProcess($url, 'Upload')) {
                $null = Resolve-PnPFolder -SiteRelativePath $folder
                $file = Add-PnPFile -Path (Join-Path $SourcePath $row.RelativePath) -Folder $folder
                $item = Get-PnPFile -Url $file.ServerRelativeUrl -AsListItem
                Set-PnPListItem -List $Library -Identity $item.Id -UpdateType UpdateOverwriteVersion -Values @{
                    Department = $row.Department; DocType = $row.DocType; LegacyPath = $row.RelativePath
                    Modified   = [datetime]::Parse($row.Modified).ToUniversalTime()
                } | Out-Null
                [pscustomobject]@{ RelativePath = $row.RelativePath; Status = 'Migrated'; Detail = ''; Url = $url }
            }
        }
        catch {
            [pscustomobject]@{ RelativePath = $row.RelativePath; Status = 'Failed'; Detail = $_.Exception.Message; Url = $url }
        }
    }
    $log | Export-Csv -Path $LogPath -NoTypeInformation -Encoding utf8
    $log
}

function Test-MgMigrationResult {
    <# Compares what should be in SharePoint (Ready rows) with what is there, per department. #>
    [CmdletBinding()] param([Parameter(Mandatory)][object[]] $Inventory, [string] $Library = 'Migrated Documents')
    $items = Get-PnPListItem -List $Library -PageSize 500 -Fields 'Department', 'FSObjType' |
             Where-Object { $_['FSObjType'] -eq 0 }
    $expected = $Inventory | Where-Object Ready | Group-Object Department -AsHashTable -AsString
    $actual   = $items | Group-Object { $_['Department'] } -AsHashTable -AsString
    $depts = @($expected.Keys) + @(if ($actual) { $actual.Keys }) | Sort-Object -Unique
    foreach ($d in $depts) {
        $e = if ($expected -and $expected[$d]) { $expected[$d].Count } else { 0 }
        $a = if ($actual -and $actual[$d]) { $actual[$d].Count } else { 0 }
        [pscustomobject]@{ Department = $d; Expected = $e; InSharePoint = $a; Match = ($e -eq $a) }
    }
}

Export-ModuleMember -Function Get-MgDepartment, Get-MgDocType, Test-MgMigrationItem, Get-MgMigrationInventory,
    Initialize-MgMigrationTarget, Invoke-MgMigration, Test-MgMigrationResult
