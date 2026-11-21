#Requires -Version 7.2
<#
.SYNOPSIS
    Writes the fictional sample PDFs for the demo: training/ has six supplier contracts (positive examples) and three
    invoices (negative examples); inbox/ has what arrives later: a contract nobody named (scan_0001.pdf), an invoice
    (scan_0002.pdf) and meeting notes. Dates are relative to -Today. The PDFs are text PDFs written by New-MgPdf,
    not scans.
.EXAMPLE
    ./New-SampleDocuments.ps1 -Path ./sample-files
#>
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Path, [datetime]$Today = (Get-Date).Date)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'MgDocProc.psm1') -Force

function New-ContractLines([string]$Number, [string]$Supplier, [string]$Service, [string]$Value, [datetime]$Start, [datetime]$End) {
    $l = @(
        'SUPPLY AGREEMENT', '',
        "Contract number: $Number", '',
        "This Supply Agreement (`"Agreement`") is made between Contoso Lda (`"Buyer`") and $Supplier (`"Supplier`").", '',
        "Effective date: $($Start.ToString('yyyy-MM-dd'))",
        "Expiry date: $($End.ToString('yyyy-MM-dd'))",
        "Contract value: EUR $Value", '',
        "1. Scope. The Supplier provides $Service to the Buyer at the Buyer's sites in Portugal.", '',
        '2. Term. This Agreement starts on the effective date and ends on the expiry date unless it is renewed in writing.', '',
        '3. Price and payment. The Buyer pays each invoice within thirty days of receipt. Prices are fixed for the term.', '',
        '4. Quality. The Supplier meets the service levels in Schedule A and reports on them every quarter.', '',
        '5. Confidentiality. Each party keeps the other party''s information confidential during and after the term.', '',
        '6. Termination. Either party may end this Agreement with ninety days written notice for material breach.', '',
        '7. Liability. Liability is limited to the contract value above, except where the law does not allow it.', '',
        '8. Governing law. This Agreement is governed by the laws of Portugal.', '',
        '9. Entire agreement. This Agreement replaces all earlier agreements on the same subject.', '',
        '10. Notices. Notices go to the contacts named in Schedule B.', '',
        'Signed for the Buyer: ______________________   Signed for the Supplier: ______________________', '',
        '(Fictional document for a demo. No real company or person.)'
    )
    # a second page of schedule text, so the files have two pages and the page meter has something to count
    $l += @('', '', 'SCHEDULE A - SERVICE LEVELS') + (1..14 | ForEach-Object { "A.$_ The Supplier answers a request within $($_ + 1) working hours and records it in the service log." })
    $l
}
function New-InvoiceLines([string]$Number, [string]$Supplier, [string]$What, [string]$Amount, [datetime]$Date) {
    @('INVOICE', '', "Invoice number: $Number", "Invoice date: $($Date.ToString('yyyy-MM-dd'))", "Supplier: $Supplier", 'Bill to: Contoso Lda', '',
      "Description: $What", "Amount due: EUR $Amount", 'Payment due within 30 days of the invoice date.', '', '(Fictional document for a demo.)')
}

$train = Join-Path $Path 'training'; $inbox = Join-Path $Path 'inbox'
New-Item -ItemType Directory -Force -Path $train, $inbox | Out-Null
$contracts = @(
    @('CTR-2026-0061', 'Fabrikam Cleaning SA', 'cleaning services', '18,000.00', 'fabrikam'),
    @('CTR-2026-0062', 'Northwind Traders', 'office supplies', '9,500.00', 'northwind'),
    @('CTR-2026-0063', 'Tailspin Toys', 'event merchandise', '4,200.00', 'tailspin'),
    @('CTR-2026-0064', 'Adventure Works', 'bicycle fleet leasing', '22,800.00', 'adventure-works'),
    @('CTR-2026-0065', 'Litware Foods', 'canteen catering', '31,000.00', 'litware'),
    @('CTR-2026-0066', 'Wingtip Toys', 'gift packaging', '6,750.00', 'wingtip')
)
$i = 0
foreach ($c in $contracts) {
    $start = $Today.AddDays(-120 + 10 * $i); $end = $start.AddYears(1).AddDays(-1)
    New-MgPdf -Path (Join-Path $train "contract-$($c[4]).pdf") -Lines (New-ContractLines $c[0] $c[1] $c[2] $c[3] $start $end)
    $i++
}
$invoices = @(@('INV-10031', 'Fabrikam Cleaning SA', 'October cleaning', '1,500.00', 'fabrikam'), @('INV-10032', 'Northwind Traders', 'Paper and toner', '320.00', 'northwind'),
    @('INV-10033', 'Litware Foods', 'Canteen, week 44', '2,140.00', 'litware'))
$d = 0
foreach ($v in $invoices) { New-MgPdf -Path (Join-Path $train "invoice-$($v[4]).pdf") -Lines (New-InvoiceLines $v[0] $v[1] $v[2] $v[3] $Today.AddDays(-20 + 3 * $d)); $d++ }

New-MgPdf -Path (Join-Path $inbox 'scan_0001.pdf') -Lines (New-ContractLines 'CTR-2026-0070' 'Proseware Ltd' 'document shredding' '3,600.00' $Today.AddDays(-5) $Today.AddYears(1).AddDays(-6))
New-MgPdf -Path (Join-Path $inbox 'scan_0002.pdf') -Lines (New-InvoiceLines 'INV-10040' 'Proseware Ltd' 'November shredding' '300.00' $Today.AddDays(-2))
New-MgPdf -Path (Join-Path $inbox 'meeting-notes.pdf') -Lines @('MEETING NOTES', '', 'Supplier review, Contoso Purchasing.', 'We talked about delivery times and the next review.', '', '(Fictional document for a demo.)')

Get-ChildItem -LiteralPath $Path -Recurse -File | Sort-Object FullName | ForEach-Object { '{0,-40} {1,6} bytes' -f $_.FullName.Substring($Path.Length).TrimStart('/', '\'), $_.Length }
