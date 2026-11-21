#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# The pure tests need nothing. The PDF writer and reader are cross-checked with qpdf when it is installed.
# The tenant tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong parameter
# name fails the test) and are skipped when PnP.PowerShell isn't installed.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
    $script:hasQpdf = [bool](Get-Command qpdf -ErrorAction SilentlyContinue)
}

BeforeAll {
    $script:src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgDocProc.psm1') -Force
    $script:plan = Import-MgJson -Path (Join-Path $src 'docproc' 'contoso-docproc.json')
    $script:bad = Import-MgJson -Path (Join-Path $src 'bad' 'bad-docproc.json')
    $script:meters = Get-MgMeter
    $script:work = Join-Path ([System.IO.Path]::GetTempPath()) "mg10-tests-$([guid]::NewGuid().ToString('N'))"
    $null = New-Item -ItemType Directory -Path $work

    function Rules($f) { @($f | Where-Object { $null -ne $_ } | ForEach-Object Rule) }
    function Copy-Json($o) { $o | ConvertTo-Json -Depth 30 | ConvertFrom-Json -Depth 30 }
    function New-Zip([string]$Path, [hashtable]$Entries) {
        Add-Type -AssemblyName System.IO.Compression
        $fs = [System.IO.File]::Create($Path)
        $zip = [System.IO.Compression.ZipArchive]::new($fs, [System.IO.Compression.ZipArchiveMode]::Create)
        foreach ($k in $Entries.Keys) {
            $e = $zip.CreateEntry($k); $w = [System.IO.StreamWriter]::new($e.Open()); $w.Write($Entries[$k]); $w.Dispose()
        }
        $zip.Dispose(); $fs.Dispose()
    }
    function New-Png([string]$Path, [int]$W, [int]$H) {
        $b = [byte[]](0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52) + [System.BitConverter]::GetBytes([int]$W)[3..0] + [System.BitConverter]::GetBytes([int]$H)[3..0] + [byte[]](8, 2, 0, 0, 0)
        [System.IO.File]::WriteAllBytes($Path, $b)
    }
    function New-Jpeg([string]$Path, [int]$W, [int]$H) {
        # SOI, an APP0 segment to step over, then SOF0 with height and width
        $app0 = [byte[]](0xFF, 0xE0, 0, 16, 0x4A, 0x46, 0x49, 0x46, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0)
        $sof = [byte[]](0xFF, 0xC0, 0, 17, 8) + [System.BitConverter]::GetBytes([uint16]$H)[1..0] + [System.BitConverter]::GetBytes([uint16]$W)[1..0] + [byte[]](3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1)
        [System.IO.File]::WriteAllBytes($Path, [byte[]](0xFF, 0xD8) + $app0 + $sof + [byte[]](0xFF, 0xD9))
    }
    function New-Sparse([string]$Path, [long]$Bytes) { $fs = [System.IO.File]::Create($Path); $fs.SetLength($Bytes); $fs.Dispose() }
}

AfterAll { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }

Describe 'PDF writer and reader' {
    It 'writes a PDF that the reader counts, one page per 46 lines' {
        $p = Join-Path $work 'three.pdf'
        New-MgPdf -Path $p -Lines (1..100 | ForEach-Object { "line $_" })
        (Get-MgPdfInfo -Path $p).Pages | Should -Be 3
    }
    It 'handles empty lines, brackets and backslashes' {
        $p = Join-Path $work 'odd.pdf'
        New-MgPdf -Path $p -Lines @('', 'a (b) c', 'back\slash', 'caf' + [char]0xE9)
        (Get-MgPdfInfo -Path $p).Pages | Should -Be 1
    }
    It 'reads the page size in inches' {
        $p = Join-Path $work 'a4.pdf'
        New-MgPdf -Path $p -Lines @('x')
        $i = Get-MgPdfInfo -Path $p
        $i.WidthIn | Should -Be 8.26
        $i.HeightIn | Should -Be 11.69
    }
    It 'agrees with qpdf on the page count and the file is structurally valid' -Skip:(-not $hasQpdf) {
        $p = Join-Path $work 'check.pdf'
        New-MgPdf -Path $p -Lines (1..120 | ForEach-Object { "line $_" })
        (& qpdf --show-npages $p) | Should -Be '3'
        & qpdf --check $p *> $null
        $LASTEXITCODE | Should -Be 0
    }
    It 'says IsPdf = false for something else' {
        $p = Join-Path $work 'not.pdf'; Set-Content $p 'hello'
        (Get-MgPdfInfo -Path $p).IsPdf | Should -BeFalse
    }
    It 'sees an encrypted PDF' {
        $p = Join-Path $work 'enc.pdf'
        Set-Content $p "%PDF-1.4`n1 0 obj << /Type /Catalog >> endobj`ntrailer << /Encrypt 5 0 R >>`n%%EOF"
        (Get-MgPdfInfo -Path $p).Encrypted | Should -BeTrue
    }
    It 'falls back to the page tree count when the page objects are compressed' {
        $p = Join-Path $work 'objstm.pdf'
        Set-Content $p "%PDF-1.5`n2 0 obj << /Type /Pages /Count 7 /Kids [3 0 R] >> endobj`n%%EOF"
        (Get-MgPdfInfo -Path $p).Pages | Should -Be 7
    }
    It 'gives Pages = $null when nothing says' {
        $p = Join-Path $work 'nothing.pdf'; Set-Content $p "%PDF-1.5`n%%EOF"
        (Get-MgPdfInfo -Path $p).Pages | Should -BeNullOrEmpty
    }
}

Describe 'Image sizes' {
    It 'reads a PNG header' { $p = Join-Path $work 'a.png'; New-Png $p 640 480; $d = Get-MgImageSize -Path $p; $d.Width | Should -Be 640; $d.Height | Should -Be 480 }
    It 'reads a JPEG header past an APP0 segment' { $p = Join-Path $work 'a.jpg'; New-Jpeg $p 1200 800; $d = Get-MgImageSize -Path $p; $d.Width | Should -Be 1200; $d.Height | Should -Be 800 }
    It 'returns $null for a file that is neither' { $p = Join-Path $work 'x.txt'; Set-Content $p 'text'; Get-MgImageSize -Path $p | Should -BeNullOrEmpty }
}

Describe 'Get-MgBillablePages (Learn: pay-as-you-go pricing)' {
    It 'unstructured: pages of a PDF' {
        $p = Join-Path $work 'u2.pdf'; New-MgPdf -Path $p -Lines (1..60 | ForEach-Object { "l$_" })
        (Get-MgBillablePages -Path $p -ModelType unstructured).Pages | Should -Be 2
    }
    It 'unstructured: pages of a Word file, from the page count Word stored' {
        $p = Join-Path $work 'a.docx'; New-Zip $p @{ 'docProps/app.xml' = '<Properties><Pages>4</Pages></Properties>' }
        (Get-MgBillablePages -Path $p -ModelType unstructured).Pages | Should -Be 4
    }
    It 'unstructured: a Word file with no stored page count is unknown, and says so' {
        $p = Join-Path $work 'b.docx'; New-Zip $p @{ 'docProps/app.xml' = '<Properties></Properties>' }
        $r = Get-MgBillablePages -Path $p -ModelType unstructured
        $r.Pages | Should -BeNullOrEmpty
        $r.Note | Should -Match 'page count'
    }
    It 'unstructured: sheets of an Excel file' {
        $p = Join-Path $work 'a.xlsx'; New-Zip $p @{ 'xl/workbook.xml' = '<workbook><sheets><sheet name="a"/><sheet name="b"/><sheet name="c"/></sheets></workbook>' }
        (Get-MgBillablePages -Path $p -ModelType unstructured).Pages | Should -Be 3
    }
    It 'unstructured: slides of a PowerPoint file' {
        $p = Join-Path $work 'a.pptx'; New-Zip $p @{ 'ppt/slides/slide1.xml' = '<a/>'; 'ppt/slides/slide2.xml' = '<a/>'; 'ppt/slideLayouts/slideLayout1.xml' = '<a/>' }
        (Get-MgBillablePages -Path $p -ModelType unstructured).Pages | Should -Be 2
    }
    It 'unstructured: one per file for text' {
        $p = Join-Path $work 'a.txt'; Set-Content $p 'hello'
        (Get-MgBillablePages -Path $p -ModelType unstructured).Pages | Should -Be 1
    }
    It 'prebuilt: pages of a PDF, one per image, nothing for a Word file' {
        $p = Join-Path $work 'pre.pdf'; New-MgPdf -Path $p -Lines (1..100 | ForEach-Object { "l$_" })
        (Get-MgBillablePages -Path $p -ModelType prebuilt-invoice).Pages | Should -Be 3
        $i = Join-Path $work 'pre.png'; New-Png $i 100 100
        (Get-MgBillablePages -Path $i -ModelType prebuilt-invoice).Pages | Should -Be 1
        (Get-MgBillablePages -Path (Join-Path $work 'a.docx') -ModelType prebuilt-invoice).Pages | Should -Be 0
    }
}

Describe 'Test-MgFile (FP001-FP006, FP008)' {
    It 'FP001: a type the model does not process' {
        $p = Join-Path $work 'x.zip'; Set-Content $p 'x'
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -Be @('FP001')
    }
    It 'FP001: prebuilt models take .jpeg, and a .jpg is only a warning' {
        $p = Join-Path $work 'w.jpg'; New-Jpeg $p 500 500
        $f = Test-MgFile -Path $p -ModelType prebuilt-receipt
        Rules $f | Should -Be @('FP001'); $f[0].Severity | Should -Be 'Warning'
    }
    It 'FP001: a Word file is fine for unstructured and not for prebuilt' {
        $p = Join-Path $work 'a.docx'
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -BeNullOrEmpty
        Rules (Test-MgFile -Path $p -ModelType prebuilt-invoice) | Should -Be @('FP001')
    }
    It 'FP002: more than 500 PDF pages for unstructured' {
        $p = Join-Path $work 'big.pdf'; New-MgPdf -Path $p -Lines (1..(46 * 501) | ForEach-Object { 'x' })
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -Contain 'FP002'
        Rules (Test-MgFile -Path $p -ModelType prebuilt-contract) | Should -Not -Contain 'FP002'
    }
    It 'FP003: a prebuilt file of 50 MB or more' {
        $p = Join-Path $work 'huge.pdf'; New-Sparse $p 50MB
        Rules (Test-MgFile -Path $p -ModelType prebuilt-invoice) | Should -Contain 'FP003'
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -Not -Contain 'FP003'
    }
    It 'FP004: images outside 50 x 50 to 10,000 x 10,000' {
        $p = Join-Path $work 'tiny.png'; New-Png $p 40 400
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -Be @('FP004')
        $p = Join-Path $work 'wide.jpg'; New-Jpeg $p 12000 800
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -Be @('FP004')
        $p = Join-Path $work 'ok.png'; New-Png $p 50 10000
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -BeNullOrEmpty
    }
    It 'FP005: a PDF page larger than 11 x 17 inches' {
        $p = Join-Path $work 'a0.pdf'; New-MgPdf -Path $p -Lines @('x') -Width 2384 -Height 3370
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -Be @('FP005')
        $p = Join-Path $work 'a3.pdf'; New-MgPdf -Path $p -Lines @('x') -Width 842 -Height 1191
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -BeNullOrEmpty   # Learn names A3 as fine
        $p = Join-Path $work 'a2.pdf'; New-MgPdf -Path $p -Lines @('x') -Width 1191 -Height 1684
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -Be @('FP005')
        $p = Join-Path $work 'tabloid.pdf'; New-MgPdf -Path $p -Lines @('x') -Width 792 -Height 1224
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -BeNullOrEmpty
    }
    It 'FP006: an encrypted PDF is a warning' {
        $f = Test-MgFile -Path (Join-Path $work 'enc.pdf') -ModelType unstructured
        Rules $f | Should -Be @('FP006'); $f[0].Severity | Should -Be 'Warning'
    }
    It 'FP008: more than 64,000 characters of text' {
        $p = Join-Path $work 'long.txt'; Set-Content $p ('x' * 64001)
        Rules (Test-MgFile -Path $p -ModelType unstructured) | Should -Be @('FP008')
    }
    It 'checks no file types for structured and freeform models' {
        Test-MgFile -Path (Join-Path $work 'x.zip') -ModelType structured | Should -BeNullOrEmpty
    }
}

Describe 'Test-MgTrainingSet (FP007)' {
    It 'unstructured: 50 MB together is the limit' {
        $a = Join-Path $work 't1.pdf'; New-Sparse $a 30MB; $b = Join-Path $work 't2.pdf'; New-Sparse $b 30MB
        Rules (Test-MgTrainingSet -Path $a, $b -ModelType unstructured) | Should -Be @('FP007')
        Rules (Test-MgTrainingSet -Path $a -ModelType unstructured) | Should -BeNullOrEmpty
    }
    It 'prebuilt: 500 pages together is the limit' {
        $a = Join-Path $work 'p1.pdf'; New-MgPdf -Path $a -Lines (1..(46 * 300) | ForEach-Object { 'x' })
        $b = Join-Path $work 'p2.pdf'; New-MgPdf -Path $b -Lines (1..(46 * 300) | ForEach-Object { 'x' })
        Rules (Test-MgTrainingSet -Path $a, $b -ModelType prebuilt-invoice) | Should -Be @('FP007')
        Rules (Test-MgTrainingSet -Path $a -ModelType prebuilt-invoice) | Should -BeNullOrEmpty
    }
}

Describe 'Cost (Learn: pay-as-you-go pricing)' {
    It 'ships the meters of the Learn table' {
        $meters.meters.unstructured.usd | Should -Be 0.005
        $meters.meters.prebuilt.usd | Should -Be 0.01
        $meters.meters.structuredFreeform.usd | Should -Be 0.05
        $meters.source | Should -Match '^https://learn.microsoft.com/'
    }
    It 'the Learn example: two models on a library, five pages, are 10 transactions' {
        $p = [pscustomobject]@{ expected = [pscustomobject]@{ docsPerMonth = 1; pagesPerDoc = 5; updatesPerDoc = 0 }
            models = @([pscustomobject]@{ name = 'A'; type = 'unstructured'; appliesTo = @('/sites/s/l') }, [pscustomobject]@{ name = 'B'; type = 'unstructured'; appliesTo = @('/sites/s/l') }) }
        $rows = Get-MgCostEstimate -Plan $p -Meters $meters
        ($rows | Measure-Object Transactions -Sum).Sum | Should -Be 10
        ($rows | Measure-Object Usd -Sum).Sum | Should -Be 0.05
    }
    It 'the Contoso plan: 40 x 3 pages x 1.5 = 180 transactions = 0.90 USD' {
        $r = @(Get-MgCostEstimate -Plan $plan)
        $r[0].Transactions | Should -Be 180
        $r[0].Usd | Should -Be 0.9
    }
    It 'counts a model once per library it is applied to' {
        $p = Copy-Json $plan; $p.models[0].appliesTo = @('/sites/a/x', '/sites/b/y')
        (Get-MgCostEstimate -Plan $p)[0].Usd | Should -Be 1.8
    }
    It 'estimates from real files: pages x (1 + updates)' {
        $rows = @([pscustomobject]@{ Pages = 2 }, [pscustomobject]@{ Pages = 3 }, [pscustomobject]@{ Pages = $null })
        (Get-MgCostEstimate -Plan $plan -Files $rows -UpdatesPerDoc 0)[0].Usd | Should -Be 0.025
    }
}

Describe 'Test-MgDocProcPlan' {
    It 'the Contoso plan is clean' { Test-MgDocProcPlan -Plan $plan | Should -BeNullOrEmpty }
    It 'the bad plan gives 8 errors and 8 warnings' {
        $f = @(Test-MgDocProcPlan -Plan $bad)
        @($f | Where-Object Severity -eq 'Error').Count | Should -Be 8
        @($f | Where-Object Severity -eq 'Warning').Count | Should -Be 8
        (Rules $f | Sort-Object -Unique) | Should -Be @('DP001', 'DP002', 'DP003', 'DP004', 'DP005', 'DP006', 'DP007', 'DP008', 'DP009')
    }
    It 'DP001: each missing billing value is reported' {
        $p = Copy-Json $plan; $p.billing.resourceGroup = ''; $p.billing.region = ''
        @(Rules (Test-MgDocProcPlan -Plan $p) | Where-Object { $_ -eq 'DP001' }).Count | Should -Be 2
    }
    It 'DP002: an enterprise model needs a content center' {
        $p = Copy-Json $plan; $p.contentCenter.url = ''
        Rules (Test-MgDocProcPlan -Plan $p) | Should -Be @('DP002')
        $p.models[0].scope = 'local'
        Rules (Test-MgDocProcPlan -Plan $p) | Should -BeNullOrEmpty
    }
    It 'DP003: five positive, one negative, five labels per extractor' {
        $p = Copy-Json $plan; $p.models[0].training.positive = 4
        Rules (Test-MgDocProcPlan -Plan $p) | Should -Be @('DP003')
        $p = Copy-Json $plan; $p.models[0].training.negative = 0
        Rules (Test-MgDocProcPlan -Plan $p) | Should -Be @('DP003')
        $p = Copy-Json $plan; $p.models[0].extractors[1].labeledFiles = 4
        Rules (Test-MgDocProcPlan -Plan $p) | Should -Be @('DP003')
    }
    It 'DP004: the prebuilt contract model is English only' {
        $p = Copy-Json $plan; $p.expected.fileTypes = @('.pdf')
        $p.models += [pscustomobject]@{ name = 'Contratos'; type = 'prebuilt-contract'; scope = 'local'; language = 'pt'; appliesTo = @('/sites/Purchasing/Contracts') }
        Rules (Test-MgDocProcPlan -Plan $p) | Should -Be @('DP004')
        $p.models[1].language = 'en'
        Rules (Test-MgDocProcPlan -Plan $p) | Should -BeNullOrEmpty
    }
    It 'DP004: the prebuilt invoice model takes Portuguese' {
        $p = Copy-Json $plan; $p.expected.fileTypes = @('.pdf')
        $p.models += [pscustomobject]@{ name = 'Faturas'; type = 'prebuilt-invoice'; scope = 'local'; language = 'pt'; appliesTo = @('/sites/Purchasing/Invoices') }
        Rules (Test-MgDocProcPlan -Plan $p) | Should -BeNullOrEmpty
    }
    It 'DP005: a library path with a subsite is a warning' {
        $p = Copy-Json $plan; $p.models[0].appliesTo = @('/sites/Purchasing/Archive/Old Invoices')
        $f = Test-MgDocProcPlan -Plan $p
        Rules $f | Should -Be @('DP005'); $f[0].Severity | Should -Be 'Warning'
    }
    It 'DP006: two models on one library' {
        $p = Copy-Json $plan
        $p.models += [pscustomobject]@{ name = 'Other'; type = 'prebuilt-invoice'; scope = 'local'; language = 'en'; appliesTo = @('/sites/Purchasing/SupplierDocuments/') }
        Rules (Test-MgDocProcPlan -Plan $p) | Should -Contain 'DP006'
    }
    It 'DP007: file types the model does not process' {
        $p = Copy-Json $plan; $p.expected.fileTypes = @('.pdf', '.zip')
        Rules (Test-MgDocProcPlan -Plan $p) | Should -Be @('DP007')
    }
    It 'DP008: over budget' {
        $p = Copy-Json $plan; $p.monthlyBudgetUsd = 0.5
        Rules (Test-MgDocProcPlan -Plan $p) | Should -Be @('DP008')
    }
    It 'DP009: structured and freeform are flagged' {
        $p = Copy-Json $plan
        $p.models += [pscustomobject]@{ name = 'Forms'; type = 'structured'; scope = 'local'; appliesTo = @('/sites/Purchasing/Forms') }
        $f = Test-MgDocProcPlan -Plan $p
        Rules $f | Should -Contain 'DP009'
        ($f | Where-Object Rule -eq 'DP009').Message | Should -Match '1 Nov 2026'
    }
}

Describe 'Get-MgExtractionReport and Test-MgLibraryLive (DL001-DL007)' {
    BeforeAll {
        $script:model = $plan.models[0]
        $script:now = [datetime]'2026-11-21T12:00:00'
        function Item([string]$Name, [string]$Ct, $Class, $Num, $Exp, $Created = '2026-11-21T10:00:00') {
            [pscustomobject]@{ Name = $Name; ContentType = $Ct; Created = [datetime]$Created; ClassificationDate = $Class; 'Contract number' = $Num; 'Expiry date' = $Exp }
        }
        function State($Items, $Cts = @([pscustomobject]@{ Name = 'Supplier Contract'; ReadOnly = $false; Sealed = $false }), $Cd = $true, $Missing = @()) {
            [pscustomobject]@{ Library = 'SupplierDocuments'; Exists = $true; ContentTypes = $Cts; HasClassificationDate = $Cd; MissingColumns = $Missing; Items = $Items }
        }
        $script:goodItems = @(
            (Item 'a.pdf' 'Supplier Contract' ([datetime]'2026-11-21T10:05:00') 'C-1' '2027-01-01'),
            (Item 'b.pdf' 'Supplier Contract' ([datetime]'2026-11-21T10:06:00') 'C-2' '2027-02-01'),
            (Item 'notes.pdf' 'Document' $null $null $null))
    }
    It 'the report counts files, classified files, and filled columns' {
        $r = Get-MgExtractionReport -Items $goodItems -ContentType 'Supplier Contract' -Columns 'Contract number', 'Expiry date'
        $r.Files | Should -Be 3; $r.Classified | Should -Be 2; $r.Unclassified | Should -Be 1; $r.OfContentType | Should -Be 2
        ($r.Columns | Where-Object Column -eq 'Expiry date').Filled | Should -Be 2
    }
    It 'a good library has no findings' {
        Test-MgLibraryLive -Model $model -State (State $goodItems) -Now $now | Should -BeNullOrEmpty
    }
    It 'DL001: no library' {
        Rules (Test-MgLibraryLive -Model $model -State ([pscustomobject]@{ Library = 'x'; Exists = $false }) -Now $now) | Should -Be @('DL001')
    }
    It 'DL002: the content type is not on the library' {
        Rules (Test-MgLibraryLive -Model $model -State (State $goodItems -Cts @()) -Now $now) | Should -Contain 'DL002'
    }
    It 'DL003: a sealed or read-only content type' {
        $ct = @([pscustomobject]@{ Name = 'Supplier Contract'; ReadOnly = $false; Sealed = $true })
        Rules (Test-MgLibraryLive -Model $model -State (State $goodItems -Cts $ct) -Now $now) | Should -Be @('DL003')
    }
    It 'DL004: no Classification Date column' {
        Rules (Test-MgLibraryLive -Model $model -State (State $goodItems -Cd $false) -Now $now) | Should -Be @('DL004')
    }
    It 'DL005: a file still not classified after 24 hours, but not one added an hour ago' {
        $items = @($goodItems) + (Item 'old.pdf' 'Document' $null $null $null '2026-11-19T10:00:00')
        $f = Test-MgLibraryLive -Model $model -State (State $items) -Now $now
        Rules $f | Should -Be @('DL005'); $f[0].Message | Should -Match 'old.pdf'
        Rules (Test-MgLibraryLive -Model $model -State (State $goodItems) -Now $now) | Should -BeNullOrEmpty
    }
    It 'DL006: a classified file with an empty extracted column' {
        $items = @($goodItems) + (Item 'c.pdf' 'Supplier Contract' ([datetime]'2026-11-21T10:07:00') 'C-3' $null)
        $f = Test-MgLibraryLive -Model $model -State (State $items) -Now $now
        Rules $f | Should -Be @('DL006'); $f[0].Message | Should -Match "1 of 3 .* 'Expiry date'"
    }
    It 'DL007: a column the extractor should have added is missing' {
        Rules (Test-MgLibraryLive -Model $model -State (State $goodItems -Missing @('Expiry date')) -Now $now) | Should -Be @('DL007')
    }
}

Describe 'Tenant functions (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
        $script:samples = Join-Path $work 'inbox'
        $null = New-Item -ItemType Directory -Path $samples
        foreach ($n in 'scan_0001.pdf', 'scan_0002.pdf', 'meeting-notes.pdf') { New-MgPdf -Path (Join-Path $samples $n) -Lines @($n) }
    }
    Context 'Send-MgSampleFiles' {
        BeforeEach {
            Mock -ModuleName MgDocProc Get-PnPFolderItem { @([pscustomobject]@{ Name = 'scan_0002.pdf' }) }
            Mock -ModuleName MgDocProc Add-PnPFile { }
        }
        It 'uploads what is not there yet, and skips what is' {
            $steps = @(Send-MgSampleFiles -Path $samples -Library 'SupplierDocuments' -Folder 'Inbox')
            $steps.Target | Should -Be @('meeting-notes.pdf', 'scan_0001.pdf')
            Should -Invoke -ModuleName MgDocProc Add-PnPFile -Times 2 -Exactly
            Should -Invoke -ModuleName MgDocProc Add-PnPFile -Times 1 -Exactly -ParameterFilter { $Folder.ServerRelativeUrl -eq 'SupplierDocuments/Inbox' -and $Path -like '*scan_0001.pdf' }
            Should -Invoke -ModuleName MgDocProc Get-PnPFolderItem -Times 1 -Exactly -ParameterFilter { $FolderSiteRelativeUrl -eq 'SupplierDocuments/Inbox' -and $ItemType -eq 'File' }
        }
        It 'uploads nothing with -WhatIf, and still lists the steps' {
            $steps = @(Send-MgSampleFiles -Path $samples -Library 'SupplierDocuments' -WhatIf)
            $steps.Count | Should -Be 2
            Should -Invoke -ModuleName MgDocProc Add-PnPFile -Times 0 -Exactly
        }
    }
    Context 'Get-MgLibraryState' {
        BeforeEach {
            Mock -ModuleName MgDocProc Get-PnPList { [pscustomobject]@{ Title = 'SupplierDocuments' } }   # PnP's List object is not constructible here; the code passes the library name on
            Mock -ModuleName MgDocProc Get-PnPContentType {
                @([pscustomobject]@{ Name = 'Document'; StringId = '0x0101'; ReadOnly = $false; Sealed = $false },
                  [pscustomobject]@{ Name = 'Supplier Contract'; StringId = '0x010100AA'; ReadOnly = $false; Sealed = $false })
            }
            Mock -ModuleName MgDocProc Get-PnPField {
                @([pscustomobject]@{ Title = 'Classification Date'; InternalName = 'ClassificationDate' },
                  [pscustomobject]@{ Title = 'Contract number'; InternalName = 'Contract_x0020_number' },
                  [pscustomobject]@{ Title = 'Name'; InternalName = 'FileLeafRef' })
            }
            Mock -ModuleName MgDocProc Get-PnPListItem {
                @([pscustomobject]@{ FieldValues = @{ FileLeafRef = 'scan_0001.pdf'; ContentType = 'Supplier Contract'; Created = [datetime]'2026-11-21T10:00:00'; ClassificationDate = [datetime]'2026-11-21T10:05:00'; Contract_x0020_number = 'C-2026-0007' } },
                  [pscustomobject]@{ FieldValues = @{ FileLeafRef = 'scan_0002.pdf'; ContentTypeId = '0x010100AA0012'; Created = [datetime]'2026-11-21T10:00:00'; ClassificationDate = [datetime]'2026-11-21T10:05:00' } },
                  [pscustomobject]@{ FieldValues = @{ FileLeafRef = 'meeting-notes.pdf'; ContentType = 'Document'; Created = [datetime]'2026-11-21T10:00:00' } })
            }
        }
        It 'resolves column titles to internal names and reads every file' {
            $s = Get-MgLibraryState -Library 'SupplierDocuments' -ColumnTitles 'Contract number', 'Expiry date'
            $s.Exists | Should -BeTrue
            $s.HasClassificationDate | Should -BeTrue
            $s.MissingColumns | Should -Be @('Expiry date')
            $s.Items.Count | Should -Be 3
            $s.Items[0].'Contract number' | Should -Be 'C-2026-0007'
            Should -Invoke -ModuleName MgDocProc Get-PnPListItem -Times 1 -Exactly -ParameterFilter { $Fields -contains 'Contract_x0020_number' -and $Fields -contains 'ClassificationDate' -and $PageSize -eq 500 }
        }
        It 'falls back to the content type id when the item has no content type name' {
            $s = Get-MgLibraryState -Library 'SupplierDocuments'
            $s.Items[1].ContentType | Should -Be 'Supplier Contract'
        }
        It 'the state feeds the lint and the report' {
            $model = $plan.models[0]
            $s = Get-MgLibraryState -Library 'SupplierDocuments' -ColumnTitles 'Contract number', 'Expiry date'
            $f = Test-MgLibraryLive -Model $model -State $s -Now ([datetime]'2026-11-21T12:00:00')
            Rules $f | Should -Contain 'DL007'
            Rules $f | Should -Contain 'DL006'
        }
        It 'says the library does not exist when PnP finds none' {
            Mock -ModuleName MgDocProc Get-PnPList { $null }
            (Get-MgLibraryState -Library 'Nope').Exists | Should -BeFalse
        }
    }
}

Describe 'Entry scripts' {
    It 'parse without errors' {
        foreach ($s in 'Invoke-DocProcessing.ps1', 'New-SampleDocuments.ps1') {
            $e = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $src $s), [ref]$null, [ref]$e)
            $e | Should -BeNullOrEmpty
        }
    }
    It 'lint and cost of the bad plan run without a tenant' {
        $out = & pwsh -NoProfile -File (Join-Path $src 'Invoke-DocProcessing.ps1') -PlanPath (Join-Path $src 'bad' 'bad-docproc.json') | Out-String
        $out | Should -Match '8 error\(s\), 8 warning\(s\)'
        $out | Should -Match 'Total per month'
    }
    It 'writes sample documents that the pre-flight accepts' {
        $dir = Join-Path $work 'samples'
        & pwsh -NoProfile -File (Join-Path $src 'New-SampleDocuments.ps1') -Path $dir | Out-Null
        (Get-ChildItem $dir -Recurse -File).Count | Should -Be 12
        $out = & pwsh -NoProfile -File (Join-Path $src 'Invoke-DocProcessing.ps1') -PlanPath (Join-Path $src 'docproc' 'contoso-docproc.json') -SamplesPath $dir | Out-String
        $out | Should -Match 'No findings'
        $out | Should -Match 'one upload of these files'
    }
    It 'refuses to touch the tenant when the plan has errors' {
        $out = & pwsh -NoProfile -File (Join-Path $src 'Invoke-DocProcessing.ps1') -PlanPath (Join-Path $src 'bad' 'bad-docproc.json') -TenantUrl 'https://contoso.sharepoint.com' 2>&1 | Out-String
        $out | Should -Match 'Fix the errors before touching the tenant'
        $LASTEXITCODE | Should -Not -Be 0
    }
}
