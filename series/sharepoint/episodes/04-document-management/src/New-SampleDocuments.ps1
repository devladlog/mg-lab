#Requires -Version 7.2
<#
.SYNOPSIS
    Writes nine small, fictional text documents for the filing demo. Expiry dates are relative to -Today, so the
    audit shows one expired, one expiring and one healthy contract whatever day you record.
.EXAMPLE
    ./New-SampleDocuments.ps1 -Path ./sample-files
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Path,
    [datetime]$Today = (Get-Date).Date
)
$d = { param([int]$days) $Today.AddDays($days).ToString('yyyy-MM-dd') }
$files = [ordered]@{
    "CTR-2026-0042 Fabrikam until $(& $d 30).txt"           = 'Cleaning services contract (fictional). Annual value 18,000 EUR.'
    "CTR-2026-0043 Northwind Traders until $(& $d 400).txt" = 'Office supplies framework agreement (fictional).'
    "CTR-2025-0107 Tailspin Toys until $(& $d -10).txt"     = 'Event merchandise contract (fictional). Expired.'
    'CTR-2026-0050 Adventure Works.txt'                     = 'Bike fleet lease (fictional). The file name has no expiry date.'
    "INV-10021 Fabrikam $(& $d -20).txt"                    = 'Invoice for October cleaning (fictional). 1,500 EUR.'
    "INV-10022 Northwind Traders $(& $d -15).txt"           = 'Invoice for paper and toner (fictional). 320 EUR.'
    'INV-10023 Northwind Traders 2026-13-01.txt'            = 'Invoice with an impossible date in its name (fictional).'
    'scan_0001.txt'                                         = 'A scanner output nobody renamed.'
    'Meeting notes.txt'                                     = 'Notes from the supplier review (fictional).'
}
New-Item -ItemType Directory -Force -Path $Path | Out-Null
foreach ($k in $files.Keys) { Set-Content -LiteralPath (Join-Path $Path $k) -Value $files[$k] -Encoding utf8 }
Get-ChildItem -LiteralPath $Path -File | Sort-Object Name
