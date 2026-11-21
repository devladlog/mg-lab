<#
.SYNOPSIS
  Proves the desktop flow really created the order: looks for it in the legacy ledger and returns the order number.
.DESCRIPTION
  The legacy application has no API, so the only reliable "output" is its ledger (CSV). A desktop flow that clicks Save
  and trusts it worked is the classic silent failure; this script reads the ledger back and returns one line of JSON
  for the PowerShell action: {"found":true,"orderNo":"PO-2026-0001","savedAtUtc":"..."}.
  Only rows saved at or after -SinceUtc are considered, so an older identical order is not mistaken for the new one.
#>
param(
    [Parameter(Mandatory)] [string] $LedgerPath,
    [string] $Supplier,
    [Parameter(Mandatory)] [string] $Amount,      # invariant, e.g. 1800.50 (produced by Test-PurchaseOrder.ps1)
    [Parameter(Mandatory)] [string] $SinceUtc,    # ISO 8601 (produced by the desktop flow's first script)
    [string] $InputDir                            # folder with Supplier.txt, written by the desktop flow (free text never goes into the script)
)
if ($InputDir) { $Supplier = [System.IO.File]::ReadAllText((Join-Path $InputDir 'Supplier.txt'), [System.Text.Encoding]::UTF8).TrimEnd("`r", "`n") }
if (-not $Supplier) { throw 'Supplier is required (-Supplier or Supplier.txt in -InputDir).' }
$inv = [System.Globalization.CultureInfo]::InvariantCulture
$out = [ordered]@{ found = $false; orderNo = ''; savedAtUtc = ''; reason = '' }
if (-not (Test-Path -LiteralPath $LedgerPath)) {
    $out.reason = 'ledger file not found'
}
else {
    $since = [datetime]::Parse($SinceUtc, $inv, [System.Globalization.DateTimeStyles]::RoundtripKind)
    $want = [decimal]::Parse($Amount, $inv)
    $row = Import-Csv -LiteralPath $LedgerPath -Encoding UTF8 |
        Where-Object {
            $_.Supplier -eq $Supplier.Trim() -and
            [decimal]::Parse($_.Amount, $inv) -eq $want -and
            [datetime]::Parse($_.SavedAtUtc, $inv, [System.Globalization.DateTimeStyles]::RoundtripKind) -ge $since
        } | Select-Object -Last 1
    if ($row) { $out.found = $true; $out.orderNo = $row.OrderNo; $out.savedAtUtc = $row.SavedAtUtc }
    else { $out.reason = 'no matching order saved since the run started' }
}
Write-Output ($out | ConvertTo-Json -Compress)
