# Provision the 'Invoices Inbox' library from the shared contract (src/docintel/columns.json) with PnP PowerShell.
# Idempotent: run it twice, the second run changes nothing.

function ConvertTo-FieldXml {
    <# Builds the CAML field definition for one contract column. Pure function: no SharePoint call. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [pscustomobject] $Column)

    $esc = { param($s) [System.Security.SecurityElement]::Escape([string]$s) }
    $name = & $esc $Column.internalName
    $display = & $esc $Column.displayName
    $indexed = if ($Column.PSObject.Properties['indexed'] -and $Column.indexed) { ' Indexed="TRUE"' } else { '' }
    $common = "ID=`"{$([guid]::NewGuid())}`" Name=`"$name`" StaticName=`"$name`" DisplayName=`"$display`"$indexed"

    switch ($Column.type) {
        'Text'     { return "<Field Type=`"Text`" $common MaxLength=`"255`" />" }
        'Note'     { return "<Field Type=`"Note`" $common NumLines=`"6`" RichText=`"FALSE`" />" }
        'Number'   { return "<Field Type=`"Number`" $common Decimals=`"2`" />" }
        'DateTime' { return "<Field Type=`"DateTime`" $common Format=`"DateOnly`" />" }
        'Choice' {
            $choices = ($Column.choices | ForEach-Object { "<CHOICE>$(& $esc $_)</CHOICE>" }) -join ''
            $default = if ($Column.PSObject.Properties['default']) { "<Default>$(& $esc $Column.default)</Default>" } else { '' }
            return "<Field Type=`"Choice`" $common Format=`"Dropdown`">$default<CHOICES>$choices</CHOICES></Field>"
        }
        default { throw "Unsupported column type '$($Column.type)' for $($Column.internalName)." }
    }
}

function Read-InvoiceContract {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "Contract not found: $Path" }
    $contract = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $dupes = $contract.columns.internalName | Group-Object | Where-Object Count -gt 1
    if ($dupes) { throw "Duplicate internal names in contract: $($dupes.Name -join ', ')" }
    return $contract
}

function Install-InvoiceInbox {
    <#
    .SYNOPSIS
      Creates the document library (if missing), turns on versioning and adds every missing column.
      Returns one object per column: Added or Exists.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [pscustomobject] $Contract)

    $title = $Contract.library
    $list = Get-PnPList -Identity $title -ErrorAction SilentlyContinue
    if (-not $list) {
        if ($PSCmdlet.ShouldProcess($title, 'Create document library')) {
            $list = New-PnPList -Title $title -Template DocumentLibrary -OnQuickLaunch
        }
    }
    if ($PSCmdlet.ShouldProcess($title, 'Enable versioning')) {
        Set-PnPList -Identity $title -EnableVersioning $true | Out-Null
    }

    foreach ($col in $Contract.columns) {
        $existing = Get-PnPField -List $title -Identity $col.internalName -ErrorAction SilentlyContinue
        if ($existing) {
            [pscustomobject]@{ Column = $col.internalName; Result = 'Exists' }
            continue
        }
        if ($PSCmdlet.ShouldProcess("$title/$($col.internalName)", "Add $($col.type) column")) {
            Add-PnPFieldFromXml -List $title -FieldXml (ConvertTo-FieldXml -Column $col) | Out-Null
            [pscustomobject]@{ Column = $col.internalName; Result = 'Added' }
        }
    }
}

Export-ModuleMember -Function ConvertTo-FieldXml, Read-InvoiceContract, Install-InvoiceInbox
