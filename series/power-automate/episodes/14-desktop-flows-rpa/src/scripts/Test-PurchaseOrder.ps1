<#
.SYNOPSIS
  Pre-flight check for the "Enter purchase order" desktop flow: validates the order the cloud flow sent and formats
  the amount the way the legacy application expects it on THIS machine.
.DESCRIPTION
  Runs inside the desktop flow's "Run PowerShell script" action (Learn: Scripting actions). Power Automate evaluates
  %variables% BEFORE the script runs, i.e. it pastes their text into the script. A supplier called  x'; calc; '  would
  become code. So the desktop flow never puts free text into the script: it writes each field to its own file with
  "Write text to file" and the action text is the fixed call
      & "C:\MGLab\scripts\Test-PurchaseOrder.ps1" -InputDir "C:\MGLab\run"
  The script reads Supplier.txt, Description.txt and Amount.txt from that folder. The action returns whatever the script
  writes with Write-Output (PowershellOutput): one line of JSON. (-Supplier/-Description/-Amount work too, for tests.)
  The cloud flow sends the amount as an invariant number ("1800.5"); the legacy form reads it with the culture of the
  machine, so we output it in that culture ("1800,50" on pt-PT). Written without PowerShell 7-only syntax.
#>
param(
    [string] $Supplier,
    [string] $Description,
    [string] $Amount,
    [string] $InputDir,
    [string] $Culture = (Get-Culture).Name
)
if ($InputDir) {
    function Read-Field([string] $Name) {
        $path = Join-Path $InputDir "$Name.txt"
        if (-not (Test-Path -LiteralPath $path)) { return '' }
        [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8).TrimEnd("`r", "`n")
    }
    $Supplier = Read-Field 'Supplier'
    $Description = Read-Field 'Description'
    $Amount = Read-Field 'Amount'
}
$MaxAmount = 100000
$MaxSupplier = 60

$errors = New-Object System.Collections.Generic.List[string]
if ([string]::IsNullOrWhiteSpace($Supplier)) { $errors.Add('Supplier is required') }
elseif ($Supplier.Trim().Length -gt $MaxSupplier) { $errors.Add("Supplier is longer than $MaxSupplier characters") }
if ([string]::IsNullOrWhiteSpace($Description)) { $errors.Add('Description is required') }

$inv = [System.Globalization.CultureInfo]::InvariantCulture
$value = 0.0
if (-not [decimal]::TryParse($Amount, [System.Globalization.NumberStyles]::Number, $inv, [ref]$value)) {
    $errors.Add('Amount is not a number')
}
elseif ($value -le 0) { $errors.Add('Amount must be greater than zero') }
elseif ($value -gt $MaxAmount) { $errors.Add("Amount is above the limit of $MaxAmount") }

try { $target = [System.Globalization.CultureInfo]::GetCultureInfo($Culture) }
catch { $errors.Add("Unknown culture '$Culture'"); $target = $inv }

$result = [ordered]@{
    valid           = ($errors.Count -eq 0)
    errors          = @($errors)
    errorText       = ($errors -join '; ')
    amountInvariant = $value.ToString('0.00', $inv)
    amountForApp    = $value.ToString('0.00', $target)
    culture         = $target.Name
}
Write-Output ($result | ConvertTo-Json -Compress)
