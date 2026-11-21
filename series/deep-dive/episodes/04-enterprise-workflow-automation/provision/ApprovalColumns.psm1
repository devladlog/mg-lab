# Adds the approval columns (contract/approval-columns.json) to the episode 1 'Invoices Inbox' library with PnP PowerShell.
# Idempotent: a second run reports Exists for every column and changes nothing.

function ConvertTo-ApprovalFieldXml {
    <# CAML for one contract column. Pure function: no SharePoint call. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [pscustomobject] $Column)

    $esc = { param($s) [System.Security.SecurityElement]::Escape([string]$s) }
    $name = & $esc $Column.internalName
    $common = "ID=`"{$([guid]::NewGuid())}`" Name=`"$name`" StaticName=`"$name`" DisplayName=`"$(& $esc $Column.displayName)`""
    switch ($Column.type) {
        'Text' { return "<Field Type=`"Text`" $common MaxLength=`"255`" />" }
        'Note' { return "<Field Type=`"Note`" $common NumLines=`"4`" RichText=`"FALSE`" />" }
        'Choice' {
            $choices = ($Column.choices | ForEach-Object { "<CHOICE>$(& $esc $_)</CHOICE>" }) -join ''
            $default = if ($Column.PSObject.Properties['default']) { "<Default>$(& $esc $Column.default)</Default>" } else { '' }
            return "<Field Type=`"Choice`" $common Format=`"Dropdown`">$default<CHOICES>$choices</CHOICES></Field>"
        }
        default { throw "Unsupported column type '$($Column.type)' for $($Column.internalName)." }
    }
}

function Read-ApprovalContract {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "Contract not found: $Path" }
    $contract = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $dupes = $contract.columns.internalName | Group-Object | Where-Object Count -gt 1
    if ($dupes) { throw "Duplicate internal names in contract: $($dupes.Name -join ', ')" }
    return $contract
}

function Install-ApprovalColumns {
    <#
    .SYNOPSIS
      Adds every missing approval column to the existing library and shows it in the default view.
      Returns one object per column: Added or Exists. Fails if the episode 1 library is not there.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [pscustomobject] $Contract)

    $title = $Contract.library
    if (-not (Get-PnPList -Identity $title -ErrorAction SilentlyContinue)) {
        throw "Library '$title' not found. Run the episode 1 provisioning (New-InvoiceInbox.ps1) first."
    }
    foreach ($col in $Contract.columns) {
        if (Get-PnPField -List $title -Identity $col.internalName -ErrorAction SilentlyContinue) {
            [pscustomobject]@{ Column = $col.internalName; Result = 'Exists' }
            continue
        }
        if ($PSCmdlet.ShouldProcess("$title/$($col.internalName)", "Add $($col.type) column")) {
            Add-PnPFieldFromXml -List $title -FieldXml (ConvertTo-ApprovalFieldXml -Column $col) | Out-Null
            [pscustomobject]@{ Column = $col.internalName; Result = 'Added' }
        }
    }
}

Export-ModuleMember -Function ConvertTo-ApprovalFieldXml, Read-ApprovalContract, Install-ApprovalColumns
