#Requires -Version 7.2
<#
.SYNOPSIS
    SharePoint Syntex, now called document processing: plan, pre-flight and cost of document processing models for
    Contoso, as code. Models themselves (the classifier, the extractors) are taught in the content center in the
    browser; nothing public creates them. What can be scripted, and tested, is everything around them:

    - lint the plan (billing, model types, training minimums, languages, libraries, budget)
    - pre-flight the files before they reach a library (file types, pages, sizes, image and page dimensions) and count
      the billable pages the way Learn's meters count them
    - estimate the monthly cost from the plan or from real files
    - read a library back and report what the models did: classified or not, extracted columns filled or empty

    Pure functions (no tenant needed): Import-MgJson, New-MgPdf, Get-MgPdfInfo, Get-MgBillablePages, Test-MgFile,
    Test-MgTrainingSet, Get-MgMeter, Get-MgCostEstimate, Test-MgDocProcPlan, Get-MgExtractionReport, Test-MgLibraryLive.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Send-MgSampleFiles, Get-MgLibraryState.
#>

Set-StrictMode -Version Latest

# ---- What Learn documents (see README "References") -------------------------------------------------------------
#   Unstructured document processing: requirements and limitations.
$script:UnstructuredTypes = @('.csv', '.doc', '.docx', '.eml', '.heic', '.heif', '.htm', '.html', '.jpeg', '.jpg', '.md', '.msg', '.pdf',
    '.png', '.ppt', '.pptx', '.rtf', '.tif', '.tiff', '.txt', '.xls', '.xlsx')
$script:TextTypes = @('.csv', '.eml', '.htm', '.html', '.md', '.rtf', '.txt')
$script:UnstructuredMaxPdfPages = 500          # OCR-scanned files: 500-page limit
$script:MaxTextCharacters = 64000              # "Truncated at 64,000 characters"
$script:TrainingMaxBytes = 50MB                # combined size of the training documents per collection
#   Prebuilt document processing: requirements and limitations (contracts, invoices, receipts, simple document).
$script:PrebuiltTypes = @('.bmp', '.jpeg', '.pdf', '.png', '.tiff')
$script:PrebuiltMaxPages = 2000                # .pdf and .tiff: up to 2,000 pages
$script:PrebuiltMaxBytes = 50MB                # "must be less than 50 MB"
$script:PrebuiltTrainingMaxPages = 500         # "total size of the training data is 500 pages or less"
$script:PrebuiltLanguages = @{
    'prebuilt-contract' = @('en')
    'prebuilt-invoice'  = @('en', 'es', 'de', 'fr', 'it', 'pt', 'nl')
    'prebuilt-receipt'  = @('en', 'hr', 'cs', 'da', 'nl', 'fi', 'de', 'hu', 'it', 'ja', 'lv', 'lt', 'no', 'pt', 'es', 'sv', 'vi')
}
$script:MinImagePixels = 50
$script:MaxImagePixels = 10000                 # images between 50 x 50 and 10,000 x 10,000
$script:MaxPdfPageInches = @(11.7, 17)         # Learn: "at most 11 x 17 inches, corresponding to Legal or A3 paper sizes and smaller"; A3 is 11.69 x 16.54 in, so the short side gets 0.7 in of room
#   Training an unstructured model: at least five positive examples and at least one negative; label five files per extractor.
$script:MinPositive = 5
$script:MinNegative = 1
$script:MinExtractorLabels = 5
#   Model types and the meter each one is billed on.
$script:ModelTypes = [ordered]@{
    'unstructured' = 'unstructured'; 'structured' = 'structuredFreeform'; 'freeform' = 'structuredFreeform'; 'structuredFreeform' = 'structuredFreeform'
    'prebuilt-contract' = 'prebuilt'; 'prebuilt-invoice' = 'prebuilt'; 'prebuilt-receipt' = 'prebuilt'
    'prebuilt-sensitive-info' = 'prebuilt'; 'prebuilt-simple' = 'prebuilt'
}

function Import-MgJson {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -Depth 30
}

function Get-MgProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    if ($Object.PSObject.Properties[$Name]) { $Object.$Name } else { $Default }
}

function New-MgFinding([string]$Rule, [string]$Severity, [string]$Target, [string]$Message) {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; Target = $Target; Message = $Message }
}

function New-MgStep([string]$Action, [string]$Target, [string]$Detail = '') {
    [pscustomobject]@{ Action = $Action; Target = $Target; Detail = $Detail }
}

# ---- PDFs: write a small valid one (for the samples), read the facts that matter --------------------------------------

function New-MgPdf {
    <# .SYNOPSIS  Writes a plain text PDF (Helvetica, A4 by default), several pages if the text needs them. ASCII text only. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][AllowEmptyString()][string[]]$Lines, [int]$LinesPerPage = 46,
          [double]$Width = 595, [double]$Height = 842)
    $latin1 = [System.Text.Encoding]::Latin1
    $pages = @(for ($i = 0; $i -lt $Lines.Count; $i += $LinesPerPage) { , @($Lines[$i..([Math]::Min($i + $LinesPerPage, $Lines.Count) - 1)]) })
    if ($pages.Count -eq 0) { $pages = @(, @('')) }
    $objs = [System.Collections.Generic.List[string]]::new()
    $firstPage = 4
    $kids = (0..($pages.Count - 1) | ForEach-Object { "$($firstPage + 2 * $_) 0 R" }) -join ' '
    $objs.Add('<< /Type /Catalog /Pages 2 0 R >>')
    $objs.Add("<< /Type /Pages /Kids [$kids] /Count $($pages.Count) >>")
    $objs.Add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    for ($p = 0; $p -lt $pages.Count; $p++) {
        $objs.Add("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 $Width $Height] /Resources << /Font << /F1 3 0 R >> >> /Contents $($firstPage + 2 * $p + 1) 0 R >>")
        $text = [System.Text.StringBuilder]::new("BT /F1 11 Tf 50 $($Height - 52) Td 15 TL`n")
        foreach ($l in $pages[$p]) {
            $esc = ($l -replace '[^\x20-\x7E]', '?').Replace('\', '\\').Replace('(', '\(').Replace(')', '\)')
            [void]$text.Append("($esc) Tj T*`n")
        }
        [void]$text.Append('ET')
        $objs.Add("<< /Length $($latin1.GetByteCount($text.ToString())) >>`nstream`n$text`nendstream")
    }
    $sb = [System.Text.StringBuilder]::new("%PDF-1.4`n")
    $offsets = @()
    for ($i = 0; $i -lt $objs.Count; $i++) {
        $offsets += $latin1.GetByteCount($sb.ToString())
        [void]$sb.Append("$($i + 1) 0 obj`n$($objs[$i])`nendobj`n")
    }
    $xref = $latin1.GetByteCount($sb.ToString())
    [void]$sb.Append("xref`n0 $($objs.Count + 1)`n0000000000 65535 f `n")
    foreach ($o in $offsets) { [void]$sb.Append(('{0:D10} 00000 n ' -f $o) + "`n") }
    [void]$sb.Append("trailer`n<< /Size $($objs.Count + 1) /Root 1 0 R >>`nstartxref`n$xref`n%%EOF`n")
    [System.IO.File]::WriteAllBytes($Path, $latin1.GetBytes($sb.ToString()))
}

function Get-MgPdfInfo {
    <#
    .SYNOPSIS  Page count, the first page size in inches, and whether the file is encrypted, read from the file's text
               structure. A PDF that keeps its page objects in compressed object streams gives Pages = $null (unknown).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $s = [System.Text.Encoding]::Latin1.GetString([System.IO.File]::ReadAllBytes($Path))
    if (-not $s.StartsWith('%PDF-')) { return [pscustomobject]@{ IsPdf = $false; Pages = $null; WidthIn = $null; HeightIn = $null; Encrypted = $false } }
    $pages = ([regex]::Matches($s, '/Type\s*/Page(?![A-Za-z])')).Count
    if ($pages -eq 0) {
        # page objects can sit in compressed object streams; a readable page tree still says /Count
        $counts = @([regex]::Matches($s, '/Type\s*/Pages[^>]*?/Count\s+(\d+)') | ForEach-Object { [int]$_.Groups[1].Value })
        $pages = if ($counts) { ($counts | Measure-Object -Maximum).Maximum } else { $null }
    }
    $mb = [regex]::Match($s, '/MediaBox\s*\[\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*\]')
    $w = $h = $null
    if ($mb.Success) {
        $w = [Math]::Round([Math]::Abs([double]$mb.Groups[3].Value - [double]$mb.Groups[1].Value) / 72, 2)
        $h = [Math]::Round([Math]::Abs([double]$mb.Groups[4].Value - [double]$mb.Groups[2].Value) / 72, 2)
    }
    [pscustomobject]@{ IsPdf = $true; Pages = $pages; WidthIn = $w; HeightIn = $h; Encrypted = ($s -match '/Encrypt\b') }
}

function Get-MgImageSize {
    <# .SYNOPSIS  Width and height in pixels of a PNG or JPEG, from the file's own header. $null for anything else. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $b = [System.IO.File]::ReadAllBytes($Path)
    if ($b.Length -ge 24 -and $b[0] -eq 0x89 -and $b[1] -eq 0x50 -and $b[2] -eq 0x4E -and $b[3] -eq 0x47) {
        return [pscustomobject]@{ Width = ([int]$b[16] * 16777216 + [int]$b[17] * 65536 + [int]$b[18] * 256 + [int]$b[19]); Height = ([int]$b[20] * 16777216 + [int]$b[21] * 65536 + [int]$b[22] * 256 + [int]$b[23]) }
    }
    if ($b.Length -ge 4 -and $b[0] -eq 0xFF -and $b[1] -eq 0xD8) {
        $i = 2
        while ($i + 9 -lt $b.Length) {
            if ($b[$i] -ne 0xFF) { $i++; continue }
            $m = $b[$i + 1]
            if ($m -in 0xC0..0xC3 + 0xC5..0xC7 + 0xC9..0xCB + 0xCD..0xCF) {
                return [pscustomobject]@{ Height = ([int]$b[$i + 5] * 256 + [int]$b[$i + 6]); Width = ([int]$b[$i + 7] * 256 + [int]$b[$i + 8]) }
            }
            if ($m -eq 0xD8 -or $m -eq 0x01 -or ($m -ge 0xD0 -and $m -le 0xD7)) { $i += 2; continue }
            $i += 2 + ([int]$b[$i + 2] * 256 + [int]$b[$i + 3])
        }
    }
    $null
}

function Read-MgZipEntry([string]$Path, [string]$Entry) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $e = $zip.GetEntry($Entry)
        if (-not $e) { return $null }
        $r = [System.IO.StreamReader]::new($e.Open())
        try { $r.ReadToEnd() } finally { $r.Dispose() }
    } finally { $zip.Dispose() }
}

function Get-MgBillablePages {
    <#
    .SYNOPSIS  What a meter counts for one file (Learn, pay-as-you-go pricing). Unstructured: pages of Word, PDF and TIFF
               files, sheets of Excel files, slides of PowerPoint files, one per file for anything else. Prebuilt and
               structured/freeform: pages of PDF files, one per image, nothing for other types.
               Count = $null when the file doesn't say (the Note tells why).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$ModelType)
    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    $meter = $script:ModelTypes[$ModelType]
    $count = 0; $note = ''
    $images = @('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff')
    if ($meter -eq 'unstructured') {
        switch ($ext) {
            '.pdf' { $i = Get-MgPdfInfo -Path $Path; $count = $i.Pages; if ($null -eq $count) { $note = 'page count not readable (compressed PDF structure)' } }
            '.docx' {
                $m = [regex]::Match("$(Read-MgZipEntry $Path 'docProps/app.xml')", '<Pages>(\d+)</Pages>')
                if ($m.Success) { $count = [int]$m.Groups[1].Value } else { $count = $null; $note = 'Word did not store a page count in this file' }
            }
            '.xlsx' { $x = Read-MgZipEntry $Path 'xl/workbook.xml'; $count = ([regex]::Matches("$x", '<sheet\s')).Count }
            '.pptx' {
                Add-Type -AssemblyName System.IO.Compression.FileSystem
                $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
                try { $count = @($zip.Entries | Where-Object { $_.FullName -match '^ppt/slides/slide\d+\.xml$' }).Count } finally { $zip.Dispose() }
            }
            { $_ -in '.tif', '.tiff' } { $count = $null; $note = 'TIFF pages are not counted here' }
            { $_ -in '.doc', '.xls', '.ppt' } { $count = $null; $note = "$ext pages, sheets and slides are not counted here" }
            default { $count = 1; $note = 'one per file' }
        }
    }
    else {
        if ($ext -eq '.pdf') { $i = Get-MgPdfInfo -Path $Path; $count = $i.Pages; if ($null -eq $count) { $note = 'page count not readable (compressed PDF structure)' } }
        elseif ($ext -in $images) { $count = 1; if ($ext -in '.tif', '.tiff') { $note = 'a multi-page TIFF counts each page; not counted here' } }
        else { $count = 0; $note = 'not processed by this model type' }
    }
    [pscustomobject]@{ Path = $Path; Name = [System.IO.Path]::GetFileName($Path); Extension = $ext; Pages = $count; Note = $note }
}

function Test-MgFile {
    <# .SYNOPSIS  Pre-flight of one file for one model type. Rules FP001-FP006 and FP008 (see README). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$ModelType)
    $f = [System.Collections.Generic.List[object]]::new()
    $name = [System.IO.Path]::GetFileName($Path)
    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    $meter = $script:ModelTypes[$ModelType]
    $prebuilt = $meter -eq 'prebuilt' -and $ModelType -ne 'prebuilt-sensitive-info'
    $supported = if ($prebuilt) { $script:PrebuiltTypes } else { $script:UnstructuredTypes }
    if ($meter -eq 'structuredFreeform') { return @() }   # file types of the AI Builder models are not checked here
    if ($ext -notin $supported) {
        if ($prebuilt -and $ext -eq '.jpg') { $f.Add((New-MgFinding 'FP001' 'Warning' $name "Learn lists .jpeg, not .jpg, for $ModelType; the format is the same, test one file.")) }
        else { $f.Add((New-MgFinding 'FP001' 'Error' $name "$ext is not supported by $ModelType.")); return $f.ToArray() }
    }
    $size = (Get-Item -LiteralPath $Path).Length
    if ($prebuilt -and $size -ge $script:PrebuiltMaxBytes) { $f.Add((New-MgFinding 'FP003' 'Error' $name "$([Math]::Round($size / 1MB, 1)) MB: the file must be less than 50 MB.")) }
    if ($ext -eq '.pdf') {
        $i = Get-MgPdfInfo -Path $Path
        $limit = if ($prebuilt) { $script:PrebuiltMaxPages } else { $script:UnstructuredMaxPdfPages }
        if ($i.Pages -and $i.Pages -gt $limit) { $f.Add((New-MgFinding 'FP002' 'Error' $name "$($i.Pages) pages: the limit is $limit.")) }
        if ($i.WidthIn -and $i.HeightIn) {
            $small, $large = ($i.WidthIn, $i.HeightIn | Sort-Object)
            if ($small -gt $script:MaxPdfPageInches[0] -or $large -gt $script:MaxPdfPageInches[1]) {
                $f.Add((New-MgFinding 'FP005' 'Error' $name "Page size $($i.WidthIn) x $($i.HeightIn) in: at most 11 x 17 in (Learn: Legal or A3 paper sizes and smaller)."))
            }
        }
        if ($i.Encrypted) { $f.Add((New-MgFinding 'FP006' 'Warning' $name 'The PDF is encrypted. If it needs a password to open, remove the lock before it goes to the library.')) }
    }
    if ($ext -in '.png', '.jpg', '.jpeg') {
        $d = Get-MgImageSize -Path $Path
        if ($d -and ($d.Width -lt $script:MinImagePixels -or $d.Height -lt $script:MinImagePixels -or $d.Width -gt $script:MaxImagePixels -or $d.Height -gt $script:MaxImagePixels)) {
            $f.Add((New-MgFinding 'FP004' 'Error' $name "$($d.Width) x $($d.Height) px: images must be between 50 x 50 and 10,000 x 10,000."))
        }
    }
    if ($meter -eq 'unstructured' -and $ext -in $script:TextTypes) {
        $chars = ([System.IO.File]::ReadAllText($Path)).Length
        if ($chars -gt $script:MaxTextCharacters) { $f.Add((New-MgFinding 'FP008' 'Warning' $name "$chars characters: the model reads the first 64,000 only.")) }
    }
    $f.ToArray()
}

function Test-MgTrainingSet {
    <# .SYNOPSIS  The example files of a model together. FP007: unstructured, more than 50 MB in total; prebuilt, more than 500 pages. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string[]]$Path, [Parameter(Mandatory)][string]$ModelType)
    $meter = $script:ModelTypes[$ModelType]
    if ($meter -eq 'unstructured') {
        $bytes = ($Path | ForEach-Object { (Get-Item -LiteralPath $_).Length } | Measure-Object -Sum).Sum
        if ($bytes -gt $script:TrainingMaxBytes) { return @(New-MgFinding 'FP007' 'Error' 'training files' "$([Math]::Round($bytes / 1MB, 1)) MB together: the training documents of one collection must not exceed 50 MB.") }
    }
    elseif ($meter -eq 'prebuilt') {
        $pages = ($Path | ForEach-Object { Get-MgBillablePages -Path $_ -ModelType $ModelType } | ForEach-Object { $_.Pages } | Where-Object { $null -ne $_ } | Measure-Object -Sum).Sum
        if ($pages -gt $script:PrebuiltTrainingMaxPages) { return @(New-MgFinding 'FP007' 'Error' 'training files' "$pages pages together: the training data must be 500 pages or less.") }
    }
    @()
}

# ---- Meters and cost -----------------------------------------------------------------------------------------------------

function Get-MgMeter {
    <# .SYNOPSIS  The meters shipped with this episode (src/docproc/meters.json): service, unit and USD per unit. #>
    [CmdletBinding()]
    param([string]$Path = (Join-Path $PSScriptRoot 'docproc' 'meters.json'))
    (Import-MgJson -Path $Path)
}

function Get-MgCostEstimate {
    <#
    .SYNOPSIS  Monthly cost of the models in a plan. Learn: processing is counted for every model applied to a library,
               on upload and on every later update, whether or not anything was classified or extracted; training is free.
               Transactions = documents x pages x (1 + updates per document), once per model on the library.
               -Files: the same arithmetic from real files (rows of Get-MgBillablePages) instead of the plan's volume.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, $Meters = (Get-MgMeter), $Files, [double]$UpdatesPerDoc = -1)
    $exp = Get-MgProp $Plan 'expected'
    $updates = if ($UpdatesPerDoc -ge 0) { $UpdatesPerDoc } else { [double](Get-MgProp $exp 'updatesPerDoc' 0) }
    $rows = foreach ($m in @(Get-MgProp $Plan 'models' @())) {
        $meterKey = $script:ModelTypes["$(Get-MgProp $m 'type' '')"]
        if (-not $meterKey) { continue }
        $rate = [double]$Meters.meters.$meterKey.usd
        $pages = if ($null -ne $Files) {
            [double](@($Files | Where-Object { $null -ne $_.Pages } | Measure-Object Pages -Sum).Sum)
        } else { [double](Get-MgProp $exp 'docsPerMonth' 0) * [double](Get-MgProp $exp 'pagesPerDoc' 1) }
        $libs = @(Get-MgProp $m 'appliesTo' @()); if ($libs.Count -eq 0) { $libs = @('(not applied)') }
        $tx = $pages * (1 + $updates)
        [pscustomobject]@{ Model = $m.name; Type = $m.type; Meter = $Meters.meters.$meterKey.service; Libraries = $libs.Count; Transactions = $tx; Rate = $rate; Usd = [Math]::Round($tx * $rate * $libs.Count, 4) }
    }
    @($rows)
}

# ---- Plan lint ----------------------------------------------------------------------------------------------------------

function Test-MgDocProcPlan {
    <# .SYNOPSIS  Lints a document processing plan before anything is set up. Rules DP001-DP009 (see README). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, $Meters = (Get-MgMeter))
    $f = [System.Collections.Generic.List[object]]::new()
    $b = Get-MgProp $Plan 'billing'
    foreach ($k in 'azureSubscription', 'resourceGroup', 'region') {
        if (-not (Get-MgProp $b $k '')) { $f.Add((New-MgFinding 'DP001' 'Error' "billing.$k" "Not set. Pay-as-you-go billing needs an Azure subscription, a resource group and a region; without billing a model can be created but not applied to a library.")) }
    }
    $models = @(Get-MgProp $Plan 'models' @())
    $exp = Get-MgProp $Plan 'expected'
    $byLib = @{}
    foreach ($m in $models) {
        $n = "$(Get-MgProp $m 'name' '')"; $t = "$(Get-MgProp $m 'type' '')"; $target = "model '$n'"
        if (-not $script:ModelTypes.Contains($t)) { $f.Add((New-MgFinding 'DP002' 'Error' $target "Type '$t': $($script:ModelTypes.Keys -join ', ').")); continue }
        if ((Get-MgProp $m 'scope' 'enterprise') -eq 'enterprise' -and -not (Get-MgProp (Get-MgProp $Plan 'contentCenter') 'url' '')) {
            $f.Add((New-MgFinding 'DP002' 'Error' $target 'An enterprise model is created in a content center, and the plan has none. Use scope local, or add a contentCenter.'))
        }
        if ($t -eq 'unstructured') {
            $tr = Get-MgProp $m 'training'
            $pos = [int](Get-MgProp $tr 'positive' 0); $neg = [int](Get-MgProp $tr 'negative' 0)
            if ($pos -lt $script:MinPositive -or $neg -lt $script:MinNegative) {
                $f.Add((New-MgFinding 'DP003' 'Error' $target "$pos positive and $neg negative example files: use at least 5 positive and at least 1 negative."))
            }
            foreach ($x in @(Get-MgProp $m 'extractors' @())) {
                if ([int](Get-MgProp $x 'labeledFiles' 0) -lt $script:MinExtractorLabels) {
                    $f.Add((New-MgFinding 'DP003' 'Error' "$target extractor '$($x.name)'" "Labeled in $([int](Get-MgProp $x 'labeledFiles' 0)) files: label the value in at least 5."))
                }
            }
        }
        if ($script:PrebuiltLanguages.ContainsKey($t)) {
            $lang = "$(Get-MgProp $m 'language' '')".ToLowerInvariant()
            if ($lang -and $lang -notin $script:PrebuiltLanguages[$t]) {
                $f.Add((New-MgFinding 'DP004' 'Error' $target "Language '$lang': $t supports $($script:PrebuiltLanguages[$t] -join ', ')."))
            }
        }
        foreach ($lib in @(Get-MgProp $m 'appliesTo' @())) {
            if ($lib -notmatch '^/(sites|teams)/[^/]+/[^/]+/?$') {
                $f.Add((New-MgFinding 'DP005' 'Warning' $target "'$lib' is not /sites/<site>/<library>: models run on sites, hub sites, sites associated with a hub and the primary site of a site collection; subsites are not supported."))
            }
            $k = $lib.TrimEnd('/').ToLowerInvariant()
            if (-not $byLib.ContainsKey($k)) { $byLib[$k] = @() }
            $byLib[$k] += $n
        }
        if ($script:ModelTypes[$t] -eq 'structuredFreeform') {
            $f.Add((New-MgFinding 'DP009' 'Warning' $target "Structured and freeform processing is the dearest meter ($($Meters.meters.structuredFreeform.usd) USD per page) and rests on AI Builder: its credits are used first, then the meter; Learn announced the end of AI Builder credits (end of life 1 Nov 2026) and says some of these capabilities are moving into Copilot in SharePoint."))
        }
        foreach ($ext in @(Get-MgProp $exp 'fileTypes' @())) {
            $meter = $script:ModelTypes[$t]
            $ok = if ($meter -eq 'unstructured' -or $t -eq 'prebuilt-sensitive-info') { $ext -in $script:UnstructuredTypes } elseif ($meter -eq 'prebuilt') { $ext -in $script:PrebuiltTypes } else { $true }
            if (-not $ok) { $f.Add((New-MgFinding 'DP007' 'Warning' $target "$ext files are expected in the library but $t does not process them.")) }
        }
    }
    foreach ($k in $byLib.Keys) {
        if ($byLib[$k].Count -gt 1) {
            $f.Add((New-MgFinding 'DP006' 'Warning' $k "$($byLib[$k].Count) models on one library ($($byLib[$k] -join ', ')): every model processes (and bills) every file, and a file is classified by the model with the highest average confidence."))
        }
    }
    $budget = [double](Get-MgProp $Plan 'monthlyBudgetUsd' 0)
    if ($budget -gt 0) {
        $est = [Math]::Round((Get-MgCostEstimate -Plan $Plan -Meters $Meters | Measure-Object Usd -Sum).Sum, 2)
        if ($est -gt $budget) { $f.Add((New-MgFinding 'DP008' 'Warning' 'monthlyBudgetUsd' "The plan costs about $est USD a month, the budget is $budget USD.")) }
    }
    $f.ToArray()
}

# ---- Read-back -----------------------------------------------------------------------------------------------------------

function Get-MgExtractionReport {
    <#
    .SYNOPSIS  What the models did to a library. Items: one object per file with ContentType, ClassificationDate and the
               extracted columns as properties. Per content type of the plan: files, classified, and for each extracted
               column how many classified files have a value.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Items, [Parameter(Mandatory)][string]$ContentType, [string[]]$Columns = @())
    $all = @($Items)
    $classified = @($all | Where-Object { Get-MgProp $_ 'ClassificationDate' })
    $typed = @($classified | Where-Object { (Get-MgProp $_ 'ContentType' '') -ieq $ContentType })
    $cols = foreach ($c in $Columns) {
        $filled = @($typed | Where-Object { "$(Get-MgProp $_ $c '')".Trim() }).Count
        [pscustomobject]@{ Column = $c; Filled = $filled; Empty = $typed.Count - $filled }
    }
    [pscustomobject]@{
        Files = $all.Count; Classified = $classified.Count; Unclassified = $all.Count - $classified.Count
        OfContentType = $typed.Count; Columns = @($cols)
    }
}

function Test-MgLibraryLive {
    <#
    .SYNOPSIS  Compares a library with the plan's model that is applied to it (state from Get-MgLibraryState). DL001-DL007.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Model, [Parameter(Mandatory)]$State, [int]$GraceHours = 24, [datetime]$Now = (Get-Date))
    $f = [System.Collections.Generic.List[object]]::new()
    $lib = "library $($State.Library)"
    if (-not $State.Exists) { return @(New-MgFinding 'DL001' 'Error' $lib 'The library does not exist.') }
    $ctName = Get-MgProp $Model 'contentType' $Model.name
    $ct = @($State.ContentTypes | Where-Object { $_.Name -ieq $ctName }) | Select-Object -First 1
    if (-not $ct) { $f.Add((New-MgFinding 'DL002' 'Error' $lib "Content type '$ctName' is not on the library: the model is not applied here (or not synced).")) }
    elseif ($ct.ReadOnly -or $ct.Sealed) { $f.Add((New-MgFinding 'DL003' 'Error' $lib "Content type '$ctName' is read-only or sealed: such a content type can't be updated, so it can't be used in a model.")) }
    if (-not $State.HasClassificationDate) { $f.Add((New-MgFinding 'DL004' 'Warning' $lib "No 'Classification Date' column: the column is added when a custom model is applied to a library.")) }
    $items = @($State.Items)
    $old = @($items | Where-Object { -not (Get-MgProp $_ 'ClassificationDate') -and (Get-MgProp $_ 'Created') -and ($Now - [datetime](Get-MgProp $_ 'Created')).TotalHours -gt $GraceHours })
    if ($State.HasClassificationDate -and $old.Count) {
        $f.Add((New-MgFinding 'DL005' 'Warning' $lib "$($old.Count) file(s) not classified $GraceHours hours after they were added: $(($old | Select-Object -First 3 | ForEach-Object { Get-MgProp $_ 'Name' '?' }) -join ', ')."))
    }
    $cols = @(@(Get-MgProp $Model 'extractors' @()) | ForEach-Object { $_.name })
    foreach ($m in @($State.MissingColumns)) { $f.Add((New-MgFinding 'DL007' 'Error' $lib "No column called '$m': the extractor is not on the library (model not synced?).")) }
    if ($State.HasClassificationDate -and $cols.Count) {
        $r = Get-MgExtractionReport -Items $items -ContentType $ctName -Columns @($cols | Where-Object { $_ -notin @($State.MissingColumns) })
        foreach ($c in $r.Columns) {
            if ($r.OfContentType -gt 0 -and $c.Empty -gt 0) {
                $f.Add((New-MgFinding 'DL006' 'Warning' $lib "$($c.Empty) of $($r.OfContentType) classified '$ctName' file(s) have no value in '$($c.Column)'."))
            }
        }
    }
    $f.ToArray()
}

# ---- Tenant functions (PnP.PowerShell) -------------------------------------------------------------------------------------

function Send-MgSampleFiles {
    <# .SYNOPSIS  Uploads the files of a folder to a library folder (Add-PnPFile), skipping what is already there. -WhatIf. #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Library, [string]$Folder = '', $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $target = if ($Folder) { "$Library/$Folder" } else { $Library }
    $have = @(Get-PnPFolderItem -FolderSiteRelativeUrl $target -ItemType File @c | ForEach-Object { $_.Name })
    foreach ($file in Get-ChildItem -LiteralPath $Path -File | Sort-Object Name) {
        if ($file.Name -in $have) { continue }
        if ($PSCmdlet.ShouldProcess($file.Name, "Upload to $target")) { $null = Add-PnPFile -Path $file.FullName -Folder $target @c }
        New-MgStep 'Upload' $file.Name $target
    }
}

function Get-MgLibraryState {
    <#
    .SYNOPSIS  Reads a library: its content types (with read-only and sealed flags) and every file with its content type,
               classification date and the extracted columns, looked up by their display names (the extractor names).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Library, [string[]]$ColumnTitles = @(), $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $list = Get-PnPList -Identity $Library @c
    if (-not $list) { return [pscustomobject]@{ Library = $Library; Exists = $false; ContentTypes = @(); HasClassificationDate = $false; MissingColumns = @(); Items = @() } }
    $cts = @(Get-PnPContentType -List $Library @c | ForEach-Object { [pscustomobject]@{ Name = $_.Name; Id = "$($_.StringId)"; ReadOnly = [bool]$_.ReadOnly; Sealed = [bool]$_.Sealed } })
    $all = @(Get-PnPField -List $Library @c)
    $cd = $all | Where-Object { $_.Title -eq 'Classification Date' } | Select-Object -First 1
    $map = [ordered]@{}; $missing = @()
    foreach ($t in $ColumnTitles) {
        $fld = $all | Where-Object { $_.Title -eq $t } | Select-Object -First 1
        if ($fld) { $map[$t] = $fld.InternalName } else { $missing += $t }
    }
    $fields = @('FileLeafRef', 'ContentType', 'ContentTypeId', 'Created') + @($map.Values)
    if ($cd) { $fields += $cd.InternalName }
    $items = @(Get-PnPListItem -List $Library -Fields $fields -PageSize 500 @c | ForEach-Object {
        $v = $_.FieldValues
        # the content type name, or (when the item doesn't carry it) the content type whose id is the longest prefix of the item's id
        $ctName = "$($v['ContentType'])"
        if (-not $ctName -and $v['ContentTypeId']) {
            $ctName = "$(($cts | Where-Object { $_.Id -and "$($v['ContentTypeId'])".StartsWith($_.Id) } | Sort-Object { $_.Id.Length } -Descending | Select-Object -First 1).Name)"
        }
        $o = [ordered]@{ Name = "$($v['FileLeafRef'])"; ContentType = $ctName; Created = $v['Created']
            ClassificationDate = $(if ($cd) { $v[$cd.InternalName] } else { $null }) }
        foreach ($t in $map.Keys) { $o[$t] = $v[$map[$t]] }
        [pscustomobject]$o
    })
    [pscustomobject]@{ Library = $Library; Exists = $true; ContentTypes = $cts; HasClassificationDate = [bool]$cd; MissingColumns = $missing; Items = $items }
}

Export-ModuleMember -Function Import-MgJson, Get-MgProp, New-MgPdf, Get-MgPdfInfo, Get-MgImageSize, Get-MgBillablePages, Test-MgFile, Test-MgTrainingSet,
    Get-MgMeter, Get-MgCostEstimate, Test-MgDocProcPlan, Get-MgExtractionReport, Test-MgLibraryLive, Send-MgSampleFiles, Get-MgLibraryState
