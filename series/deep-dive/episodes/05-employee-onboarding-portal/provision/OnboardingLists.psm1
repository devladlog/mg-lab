# Creates the two onboarding lists from contract/onboarding-lists.json with PnP PowerShell.
# Idempotent: lists and columns that exist are reported as Exists and left alone; indexed columns get an index.

function Read-OnboardingContract {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "Contract not found: $Path" }
    $contract = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    foreach ($list in $contract.lists) {
        $dupes = $list.columns.internalName | Group-Object | Where-Object Count -gt 1
        if ($dupes) { throw "Duplicate internal names in '$($list.title)': $($dupes.Name -join ', ')" }
        foreach ($c in $list.columns) {
            if ($c.internalName -notmatch '^[A-Za-z][A-Za-z0-9]{0,31}$') { throw "Internal name '$($c.internalName)' must be letters/digits, max 32." }
        }
    }
    return $contract
}

function ConvertTo-OnboardingFieldXml {
    <# CAML for one contract column. Pure function: no SharePoint call. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [pscustomobject] $Column)

    $esc = { param($s) [System.Security.SecurityElement]::Escape([string]$s) }
    $name = & $esc $Column.internalName
    $required = if ($Column.PSObject.Properties['required'] -and $Column.required) { 'TRUE' } else { 'FALSE' }
    $indexed = if ($Column.PSObject.Properties['indexed'] -and $Column.indexed) { ' Indexed="TRUE"' } else { '' }
    $common = "ID=`"{$([guid]::NewGuid())}`" Name=`"$name`" StaticName=`"$name`" DisplayName=`"$(& $esc $Column.displayName)`" Required=`"$required`"$indexed"
    $default = if ($Column.PSObject.Properties['default']) { "<Default>$(& $esc $Column.default)</Default>" } else { '' }
    switch ($Column.type) {
        'Text'     { return "<Field Type=`"Text`" $common MaxLength=`"255`">$default</Field>" }
        'Note'     { return "<Field Type=`"Note`" $common NumLines=`"4`" RichText=`"FALSE`" />" }
        'Number'   { return "<Field Type=`"Number`" $common Decimals=`"0`" />" }
        'Boolean'  { return "<Field Type=`"Boolean`" $common>$default</Field>" }
        'DateOnly' { return "<Field Type=`"DateTime`" $common Format=`"DateOnly`" />" }
        'DateTime' { return "<Field Type=`"DateTime`" $common Format=`"DateTime`" />" }
        'Choice' {
            $choices = ($Column.choices | ForEach-Object { "<CHOICE>$(& $esc $_)</CHOICE>" }) -join ''
            return "<Field Type=`"Choice`" $common Format=`"Dropdown`">$default<CHOICES>$choices</CHOICES></Field>"
        }
        default { throw "Unsupported column type '$($Column.type)' for $($Column.internalName)." }
    }
}

function Install-OnboardingLists {
    <#
    .SYNOPSIS
      Creates missing lists and columns; columns marked "indexed" get Indexed="TRUE" in their CAML.
      Returns one object per list/column: Added or Exists.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)] [pscustomobject] $Contract)

    foreach ($list in $Contract.lists) {
        $existing = Get-PnPList -Identity $list.title -ErrorAction SilentlyContinue
        if ($existing) {
            [pscustomobject]@{ List = $list.title; Column = ''; Result = 'Exists' }
        }
        elseif ($PSCmdlet.ShouldProcess($list.title, 'Create list')) {
            New-PnPList -Title $list.title -Template GenericList -EnableVersioning | Out-Null
            Set-PnPList -Identity $list.title -Description $list.description | Out-Null
            [pscustomobject]@{ List = $list.title; Column = ''; Result = 'Added' }
        }
        else { continue }   # -WhatIf on a missing list: nothing below can run

        foreach ($col in $list.columns) {
            if (Get-PnPField -List $list.title -Identity $col.internalName -ErrorAction SilentlyContinue) {
                [pscustomobject]@{ List = $list.title; Column = $col.internalName; Result = 'Exists' }
                continue
            }
            if ($PSCmdlet.ShouldProcess("$($list.title)/$($col.internalName)", "Add $($col.type) column")) {
                Add-PnPFieldFromXml -List $list.title -FieldXml (ConvertTo-OnboardingFieldXml -Column $col) | Out-Null
                [pscustomobject]@{ List = $list.title; Column = $col.internalName; Result = 'Added' }
            }
        }
    }
}

Export-ModuleMember -Function Read-OnboardingContract, ConvertTo-OnboardingFieldXml, Install-OnboardingLists
