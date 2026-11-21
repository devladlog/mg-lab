#Requires -Version 7.2
<#
.SYNOPSIS
    Document management as code: site columns, content types (with correct IDs), a document set per supplier and
    a library, all from one JSON design; a filing plan that turns file names into content type + metadata before
    upload; and an audit of what is really in the library (missing required metadata, untyped files, stale
    check-outs, expiring contracts, missing document IDs).

    Pure functions (no SharePoint needed): Import-MgJson, Test-MgContentTypeId, New-MgContentTypeId,
    Get-MgEffectiveField, Test-MgDocDesign, Test-MgFilingPlan, Resolve-MgFilingPlan, ConvertTo-MgSiteColumnXml,
    ConvertFrom-MgListItem, Test-MgDocumentItem.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Invoke-MgDocMgmtProvisioning, Invoke-MgFiling,
    Get-MgLibraryAudit.
#>

Set-StrictMode -Version Latest

# ---- What Learn documents (see README "References") -------------------------------------------------------------
#   Content type ID = parent ID + two hex digits (not "00"), or parent ID + "00" + GUID (no punctuation).
#   Use the GUID form for direct children of content types you didn't create. Max 512 bytes = 1,024 characters.
#   A content type ID must be unique within a site collection.
#   Item 0x01, Document 0x0101, Folder 0x0120, Document Set 0x0120D520.
#   Site collection features: Document ID Service B50E3104-6812-424F-A011-CC90E6327318,
#                             Document Sets       3BAE86A2-776D-499D-9DB8-FA4CDC7884F8.
$script:BuiltInContentTypes = [ordered]@{ 'Item' = '0x01'; 'Document' = '0x0101'; 'Folder' = '0x0120'; 'Document Set' = '0x0120D520' }
$script:Features = @{
    DocumentId   = [guid]'B50E3104-6812-424F-A011-CC90E6327318'
    DocumentSets = [guid]'3BAE86A2-776D-499D-9DB8-FA4CDC7884F8'
}
$script:MaxContentTypeIdLength = 1024
$script:DocumentSetId = '0x0120D520'
$script:FieldTypes = @('Text', 'Note', 'Choice', 'DateTime', 'Currency', 'Number', 'Boolean')

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

function Get-MgFeatureId { [CmdletBinding()] param([ValidateSet('DocumentId', 'DocumentSets')][string]$Name) $script:Features[$Name] }

# ---- Content type IDs ---------------------------------------------------------------------------------------------

function New-MgContentTypeId {
    <#
    .SYNOPSIS  Builds a child content type ID: parent + "00" + GUID (default), or parent + two hex digits (-Suffix).
    #>
    [CmdletBinding(DefaultParameterSetName = 'Guid')]
    param(
        [Parameter(Mandatory)][string]$ParentId,
        [Parameter(ParameterSetName = 'Guid')][guid]$Guid = [guid]::NewGuid(),
        [Parameter(ParameterSetName = 'Suffix', Mandatory)][ValidatePattern('^[0-9A-Fa-f]{2}$')][string]$Suffix
    )
    if ($PSCmdlet.ParameterSetName -eq 'Suffix') {
        if ($Suffix -eq '00') { throw "A two-digit suffix can't be '00'." }
        return "$ParentId$($Suffix.ToUpperInvariant())"
    }
    "${ParentId}00$($Guid.ToString('N').ToUpperInvariant())"
}

function Test-MgContentTypeId {
    <#
    .SYNOPSIS  Checks a content type ID against Learn's rules. Returns findings (empty = valid).
    .PARAMETER ParentId  When given, the lineage and the suffix are checked too.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Id, [string]$ParentId, [string]$Target = $Id)
    if ($Id -notmatch '^0x([0-9A-Fa-f]{2})+$') {
        New-MgFinding 'DM001' 'Error' $Target "'$Id' isn't a content type ID: '0x' followed by pairs of hexadecimal digits."
        return
    }
    if ($Id.Length -gt $script:MaxContentTypeIdLength) {
        New-MgFinding 'DM002' 'Error' $Target "$($Id.Length) characters; a content type ID is at most 512 bytes ($($script:MaxContentTypeIdLength) characters)."
    }
    if (-not $ParentId) { return }
    if (-not $Id.StartsWith($ParentId, [StringComparison]::OrdinalIgnoreCase) -or $Id.Length -eq $ParentId.Length) {
        New-MgFinding 'DM003' 'Error' $Target "'$Id' doesn't start with its parent's ID '$ParentId': the ID must encode the lineage."
        return
    }
    $suffix = $Id.Substring($ParentId.Length)
    if ($suffix.Length -eq 2) {
        if ($suffix -eq '00') {
            New-MgFinding 'DM004' 'Error' $Target "The two hexadecimal digits after the parent ID can't be '00'."
        }
        elseif ($ParentId -in $script:BuiltInContentTypes.Values) {
            New-MgFinding 'DM005' 'Warning' $Target "Direct child of a built-in content type with a two-digit suffix. Use parent + '00' + GUID, so a future built-in type can't collide with it."
        }
    }
    elseif ($suffix -notmatch '^00[0-9A-Fa-f]{32}$') {
        New-MgFinding 'DM004' 'Error' $Target "After the parent ID comes either two hex digits (not '00') or '00' + a 32-digit GUID; got '$suffix'."
    }
}

# ---- Design ------------------------------------------------------------------------------------------------------

function Get-MgContentTypeIndex($Design) {
    $byName = [ordered]@{}
    foreach ($ct in @(Get-MgProp $Design 'contentTypes' @())) { if (-not $byName.Contains($ct.name)) { $byName[$ct.name] = $ct } }
    $byName
}

function Get-MgParentId($Design, $ContentType) {
    $p = Get-MgProp $ContentType 'parent' 'Document'
    if ($script:BuiltInContentTypes.Contains($p)) { return $script:BuiltInContentTypes[$p] }
    $idx = Get-MgContentTypeIndex $Design
    if ($idx.Contains($p)) { return $idx[$p].id }
    $null
}

function Test-MgIsDocumentSet($Design, $ContentType) {
    "$($ContentType.id)".StartsWith($script:DocumentSetId, [StringComparison]::OrdinalIgnoreCase)
}

function Get-MgEffectiveField {
    <#
    .SYNOPSIS  The fields of a content type including those inherited from its parents in the design.
               Returns objects with Name and Required (required wins if any level requires it).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Design, [Parameter(Mandatory)][string]$ContentTypeName)
    $idx = Get-MgContentTypeIndex $Design
    $chain = @(); $name = $ContentTypeName; $guard = 0
    while ($name -and $idx.Contains($name) -and $guard++ -lt 20) { $chain += $idx[$name]; $name = Get-MgProp $idx[$name] 'parent' $null }
    $fields = [ordered]@{}
    [array]::Reverse($chain)
    foreach ($ct in $chain) {
        foreach ($f in @(Get-MgProp $ct 'fields' @())) {
            $req = [bool](Get-MgProp $f 'required' $false)
            if ($fields.Contains($f.name)) { $fields[$f.name] = $fields[$f.name] -or $req } else { $fields[$f.name] = $req }
        }
    }
    foreach ($k in $fields.Keys) { [pscustomobject]@{ Name = $k; Required = $fields[$k] } }
}

function Test-MgDocDesign {
    <#
    .SYNOPSIS  Lints a document management design. With -Plan, required fields covered by the filing plan count
               as covered (rule DM013).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Design, $Plan)
    $columns = @{}; foreach ($c in @(Get-MgProp $Design 'siteColumns' @())) { $columns[$c.internalName] = $c }
    $features = Get-MgProp $Design 'features'
    $docSetsOn = [bool](Get-MgProp $features 'documentSets' $false)
    $docIdOn = [bool](Get-MgProp $features 'documentId' $false)

    foreach ($c in @(Get-MgProp $Design 'siteColumns' @())) {
        if (-not (Get-MgProp $c 'id')) {
            New-MgFinding 'DM015' 'Warning' "column $($c.internalName)" "No 'id': re-running provisioning can't recognise the column by ID. Give every site column a random GUID."
        }
        if ((Get-MgProp $c 'type' '') -notin $script:FieldTypes) {
            New-MgFinding 'DM007' 'Error' "column $($c.internalName)" "Type '$($c.type)' isn't supported by this design ($($script:FieldTypes -join ', '))."
        }
    }

    $seenIds = @{}; $seenNames = @{}
    $idx = Get-MgContentTypeIndex $Design
    foreach ($ct in @(Get-MgProp $Design 'contentTypes' @())) {
        $t = "content type '$($ct.name)'"
        if ($seenNames.ContainsKey($ct.name)) { New-MgFinding 'DM006' 'Error' $t "Two content types are named '$($ct.name)'." }
        $seenNames[$ct.name] = $true
        if ($seenIds.ContainsKey("$($ct.id)".ToUpperInvariant())) { New-MgFinding 'DM006' 'Error' $t "ID '$($ct.id)' is used twice: content type IDs are unique within a site collection." }
        $seenIds["$($ct.id)".ToUpperInvariant()] = $true

        $parentId = Get-MgParentId $Design $ct
        if (-not $parentId) {
            New-MgFinding 'DM003' 'Error' $t "Parent '$(Get-MgProp $ct 'parent' '')' is neither a built-in content type ($($script:BuiltInContentTypes.Keys -join ', ')) nor in this design."
            Test-MgContentTypeId -Id $ct.id -Target $t
        }
        else { Test-MgContentTypeId -Id $ct.id -ParentId $parentId -Target $t }

        foreach ($f in @(Get-MgProp $ct 'fields' @())) {
            if (-not $columns.ContainsKey($f.name)) {
                New-MgFinding 'DM007' 'Error' $t "Field '$($f.name)' isn't one of the design's site columns."
            }
        }

        $ds = Get-MgProp $ct 'documentSet'
        if ((Test-MgIsDocumentSet $Design $ct) -or $ds) {
            if (-not $docSetsOn) {
                New-MgFinding 'DM008' 'Error' $t 'Document set content type, but the Document Sets site collection feature is off. Enable it first.'
            }
            foreach ($a in @(Get-MgProp $ds 'allowedContentTypes' @())) {
                if (-not $idx.Contains($a) -and -not $script:BuiltInContentTypes.Contains($a)) {
                    New-MgFinding 'DM009' 'Error' $t "Allowed content type '$a' doesn't exist in the design."
                }
            }
            foreach ($s in @(Get-MgProp $ds 'sharedFields' @())) {
                if (-not $columns.ContainsKey($s)) { New-MgFinding 'DM009' 'Error' $t "Shared field '$s' isn't one of the design's site columns." }
            }
        }
    }

    if ($docIdOn -and [bool](Get-MgProp $Design 'contentTypeHub' $false)) {
        New-MgFinding 'DM011' 'Warning' 'features' 'Document IDs with content types from the content type hub: enable the Document ID Service on the hub first and republish, or subscriber sites never assign IDs.'
    }

    foreach ($lib in @(Get-MgProp $Design 'libraries' @())) {
        $t = "library '$($lib.title)'"
        $libCts = @(Get-MgProp $lib 'contentTypes' @())
        foreach ($n in $libCts) {
            if (-not $idx.Contains($n) -and -not $script:BuiltInContentTypes.Contains($n)) {
                New-MgFinding 'DM012' 'Error' $t "Content type '$n' doesn't exist in the design."
            }
        }
        $def = Get-MgProp $lib 'defaultContentType'
        if ($def -and $def -notin $libCts) {
            New-MgFinding 'DM012' 'Error' $t "Default content type '$def' isn't one of the library's content types."
        }
        if ([bool](Get-MgProp $lib 'requireCheckout' $false)) {
            New-MgFinding 'DM010' 'Warning' $t 'Require check-out is on: a checked-out document is locked, so nobody can co-author it.'
        }

        $libFields = @{}
        foreach ($n in $libCts) { if ($idx.Contains($n)) { foreach ($f in Get-MgEffectiveField $Design $n) { $libFields[$f.Name] = $true } } }
        $defaults = @{}
        foreach ($d in @(Get-MgProp $lib 'defaultValues' @())) {
            if (-not $libFields.ContainsKey($d.field)) {
                New-MgFinding 'DM014' 'Warning' $t "Default value for '$($d.field)', which no content type of this library has."
            }
            else { $defaults[$d.field] = $true }
        }

        # DM013: a required field nobody fills. Browser uploads in the modern library don't prompt for it.
        $planRules = @(); $folderCt = $null
        if ($Plan -and (Get-MgProp $Plan 'library') -eq $lib.title) {
            $planRules = @(Get-MgProp $Plan 'rules' @()); $folderCt = Get-MgProp $Plan 'folderContentType'
        }
        foreach ($n in $libCts) {
            if (-not $idx.Contains($n)) { continue }
            $covered = @{} + $defaults
            foreach ($r in $planRules | Where-Object { $_.contentType -eq $n }) {
                foreach ($g in ([regex]$r.match).GetGroupNames()) { $covered[$g] = $true }
                foreach ($k in @((Get-MgProp $r 'values' ([pscustomobject]@{})).PSObject.Properties | ForEach-Object Name)) { $covered[$k] = $true }
            }
            if ($n -eq $folderCt) {
                foreach ($r in $planRules) { foreach ($m in [regex]::Matches("$(Get-MgProp $r 'folder' '')", '\{(\w+)\}')) { $covered[$m.Groups[1].Value] = $true } }
            }
            foreach ($f in Get-MgEffectiveField $Design $n | Where-Object Required) {
                if (-not $covered.ContainsKey($f.Name)) {
                    New-MgFinding 'DM013' 'Warning' "$t / $n" "Required field '$($f.Name)' has no default value and no filing rule sets it. Uploads through the browser won't prompt for it, so files arrive incomplete."
                }
            }
        }
    }
}

function Test-MgFilingPlan {
    <# .SYNOPSIS  Lints a filing plan against the design. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)]$Design)
    $lib = @(Get-MgProp $Design 'libraries' @()) | Where-Object title -eq $Plan.library | Select-Object -First 1
    if (-not $lib) { New-MgFinding 'FP002' 'Error' 'plan' "Library '$($Plan.library)' isn't in the design."; return }
    $folderCt = Get-MgProp $Plan 'folderContentType'
    if ($folderCt -and $folderCt -notin @($lib.contentTypes)) {
        New-MgFinding 'FP002' 'Error' 'plan' "Folder content type '$folderCt' isn't one of the library's content types."
    }
    foreach ($r in @(Get-MgProp $Plan 'rules' @())) {
        $t = "rule '$($r.name)'"
        try { $rx = [regex]::new($r.match) } catch { New-MgFinding 'FP001' 'Error' $t "Invalid regular expression: $($_.Exception.InnerException.Message)"; continue }
        if ($r.contentType -notin @($lib.contentTypes)) {
            New-MgFinding 'FP002' 'Error' $t "Content type '$($r.contentType)' isn't one of the library's content types."; continue
        }
        $fields = @(Get-MgEffectiveField $Design $r.contentType | ForEach-Object Name)
        foreach ($g in $rx.GetGroupNames() | Where-Object { $_ -notmatch '^\d+$' }) {
            if ($g -notin $fields) { New-MgFinding 'FP003' 'Error' $t "Group '$g' isn't a field of '$($r.contentType)'." }
        }
        foreach ($m in [regex]::Matches("$(Get-MgProp $r 'folder' '')", '\{(\w+)\}')) {
            if ($m.Groups[1].Value -notin $rx.GetGroupNames()) { New-MgFinding 'FP004' 'Error' $t "Folder token '{$($m.Groups[1].Value)}' isn't a group of the expression." }
        }
    }
}

function Resolve-MgFilingPlan {
    <#
    .SYNOPSIS  Decides, for each file name, the content type, the folder (document set) and the metadata.
               Status: Ready, Incomplete (a required field has no value), Invalid (a value doesn't parse), Unmatched.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)]$Design, [Parameter(Mandatory)][string[]]$FileName)
    $lib = @($Design.libraries) | Where-Object title -eq $Plan.library | Select-Object -First 1
    $defaults = @{}; foreach ($d in @(Get-MgProp $lib 'defaultValues' @())) { $defaults[$d.field] = $d.value }
    $columns = @{}; foreach ($c in @($Design.siteColumns)) { $columns[$c.internalName] = $c }

    foreach ($name in $FileName) {
        $hit = $null; $m = $null
        foreach ($r in @($Plan.rules)) {
            $m = [regex]::Match($name, $r.match)
            if ($m.Success) { $hit = $r; break }
        }
        if (-not $hit) {
            [pscustomobject]@{ FileName = $name; Rule = $null; ContentType = $null; Folder = $null; Values = [ordered]@{}; Missing = @(); Status = 'Unmatched'; Problem = 'No filing rule matches the name.' }
            continue
        }
        $values = [ordered]@{}
        foreach ($g in $m.Groups | Where-Object { $_.Success -and $_.Name -notmatch '^\d+$' }) { $values[$g.Name] = $g.Value.Trim() }
        foreach ($p in @((Get-MgProp $hit 'values' ([pscustomobject]@{})).PSObject.Properties)) { $values[$p.Name] = $p.Value }

        $problem = $null
        foreach ($k in @($values.Keys)) {
            $type = Get-MgProp $columns[$k] 'type' 'Text'
            if ($type -eq 'DateTime') {
                $dt = [datetime]::MinValue
                if (-not [datetime]::TryParseExact($values[$k], 'yyyy-MM-dd', [cultureinfo]::InvariantCulture, 'None', [ref]$dt)) { $problem = "'$($values[$k])' isn't a date (yyyy-MM-dd) for $k." }
            }
            elseif ($type -in 'Currency', 'Number') {
                $d = 0.0
                if (-not [double]::TryParse($values[$k], [Globalization.NumberStyles]::Float, [cultureinfo]::InvariantCulture, [ref]$d)) { $problem = "'$($values[$k])' isn't a number for $k." }
            }
        }
        $folder = [regex]::Replace("$(Get-MgProp $hit 'folder' '')", '\{(\w+)\}', { param($x) "$($values[$x.Groups[1].Value])" })
        $missing = @(Get-MgEffectiveField $Design $hit.contentType | Where-Object { $_.Required -and -not $values.Contains($_.Name) -and -not $defaults.ContainsKey($_.Name) } | ForEach-Object Name)
        $status = if ($problem) { 'Invalid' } elseif ($missing) { 'Incomplete' } else { 'Ready' }
        if (-not $problem -and $missing) { $problem = "Missing required: $($missing -join ', ')." }
        [pscustomobject]@{ FileName = $name; Rule = $hit.name; ContentType = $hit.contentType; Folder = $folder; Values = $values; Missing = $missing; Status = $status; Problem = $problem }
    }
}

function ConvertTo-MgSiteColumnXml {
    <# .SYNOPSIS  Field XML for a site column: clean internal name, friendly display name, fixed ID. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Column, [string]$Group = 'Contoso Purchasing')
    $enc = { param($s) [System.Security.SecurityElement]::Escape([string]$s) }
    $n = $Column.internalName
    $attrs = [ordered]@{ Type = $Column.type; ID = "{$($Column.id)}"; Name = $n; StaticName = $n; DisplayName = $Column.displayName; Group = $Group; Required = 'FALSE' }
    $inner = ''
    switch ($Column.type) {
        'Text' { $attrs.MaxLength = '255' }
        'DateTime' { if (Get-MgProp $Column 'dateOnly' $false) { $attrs.Format = 'DateOnly' } }
        'Currency' { $attrs.LCID = "$(Get-MgProp $Column 'lcid' -2)"; $attrs.Decimals = '2' }   # -2 = euro, symbol after the number
        'Choice' {
            $attrs.Format = 'Dropdown'
            $inner = '<CHOICES>' + ((@($Column.choices) | ForEach-Object { "<CHOICE>$(& $enc $_)</CHOICE>" }) -join '') + '</CHOICES>'
        }
    }
    $a = ($attrs.GetEnumerator() | ForEach-Object { "$($_.Key)=`"$(& $enc $_.Value)`"" }) -join ' '
    if ($inner) { "<Field $a>$inner</Field>" } else { "<Field $a />" }
}

# ---- Audit -------------------------------------------------------------------------------------------------------

function ConvertFrom-MgListItem {
    <# .SYNOPSIS  Flattens a list item (CSOM ListItem from Get-PnPListItem -IncludeContentType) for the audit. #>
    [CmdletBinding()]
    param([Parameter(Mandatory, ValueFromPipeline)]$Item)
    process {
        $v = $Item.FieldValues
        $checkout = Get-MgProp $v 'CheckoutUser'
        [pscustomobject]@{
            Name         = Get-MgProp $v 'FileLeafRef'
            Folder       = Get-MgProp $v 'FileDirRef'
            IsFolder     = "$(Get-MgProp $v 'FSObjType' 0)" -eq '1'
            ContentType  = "$(Get-MgProp $Item.ContentType 'Name' '')"
            Values       = $v
            CheckedOutTo = if ($checkout) { "$(Get-MgProp $checkout 'LookupValue' $checkout)" } else { $null }
            Modified     = [datetime](Get-MgProp $v 'Modified' ([datetime]::MinValue))
            DocId        = Get-MgProp $v '_dlc_DocId'
        }
    }
}

function Test-MgDocumentItem {
    <#
    .SYNOPSIS  Audits library items (from ConvertFrom-MgListItem, or test objects with the same shape).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][object[]]$Items,
        [Parameter(Mandatory)]$Design,
        [Parameter(Mandatory)][string]$Library,
        [datetime]$Today = (Get-Date).Date,
        [int]$ExpiryWarningDays = 60,
        [int]$StaleCheckoutDays = 14
    )
    $lib = @($Design.libraries) | Where-Object title -eq $Library | Select-Object -First 1
    $allowed = @(Get-MgProp $lib 'contentTypes' @())
    $docIdOn = [bool](Get-MgProp (Get-MgProp $Design 'features') 'documentId' $false)
    $idx = Get-MgContentTypeIndex $Design

    foreach ($i in $Items) {
        $t = if ($i.Folder) { "$($i.Folder)/$($i.Name)" } else { $i.Name }
        if ($i.ContentType -notin $allowed) {
            New-MgFinding 'DA002' 'Warning' $t "Content type '$($i.ContentType)' isn't one of the library's ($($allowed -join ', ')): the file has no proper type and none of its metadata."
        }
        elseif ($idx.Contains($i.ContentType)) {
            foreach ($f in Get-MgEffectiveField $Design $i.ContentType | Where-Object Required) {
                $val = Get-MgProp $i.Values $f.Name
                if ($null -eq $val -or "$val" -eq '') {
                    New-MgFinding 'DA001' 'Error' $t "Required '$($f.Name)' is empty."
                }
            }
        }
        if ($i.IsFolder) { continue }
        if ($i.CheckedOutTo -and ($Today - $i.Modified.Date).TotalDays -gt $StaleCheckoutDays) {
            New-MgFinding 'DA003' 'Warning' $t "Checked out to $($i.CheckedOutTo) and unchanged for $([int]($Today - $i.Modified.Date).TotalDays) days: nobody else can edit it."
        }
        $exp = Get-MgProp $i.Values 'ExpiryDate'
        if ($exp) {
            $days = ([datetime]$exp).Date - $Today
            if ($days.TotalDays -lt 0) { New-MgFinding 'DA005' 'Error' $t "Expired on $(([datetime]$exp).ToString('yyyy-MM-dd'))." }
            elseif ($days.TotalDays -le $ExpiryWarningDays) { New-MgFinding 'DA004' 'Warning' $t "Expires in $([int]$days.TotalDays) days ($(([datetime]$exp).ToString('yyyy-MM-dd')))." }
        }
        if ($docIdOn -and -not $i.DocId) {
            New-MgFinding 'DA006' 'Warning' $t 'No document ID although the Document ID Service is on (on sites that use the content type hub, see DM011).'
        }
    }
}

function Invoke-MgQuiet([scriptblock]$Block) {
    # 'Not found' is an answer, not an error: PnP throws for some missing objects and returns nothing for others.
    try { & $Block } catch { $null }
}

function New-MgStep([string]$Action, [string]$Target, [string]$Detail = '') {
    [pscustomobject]@{ Action = $Action; Target = $Target; Detail = $Detail }
}

# ---- Tenant functions (PnP.PowerShell) --------------------------------------------------------------------------

function Invoke-MgDocMgmtProvisioning {
    <#
    .SYNOPSIS  Features, site columns, content types (with their IDs), the document set, then the library.
               Idempotent: creates only what's missing. Honours -WhatIf.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Design, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $f = Get-MgProp $Design 'features'

    foreach ($name in 'DocumentSets', 'DocumentId') {
        $on = [bool](Get-MgProp $f ($name.Substring(0, 1).ToLower() + $name.Substring(1)) $false)
        if (-not $on) { continue }
        $id = $script:Features[$name]
        $active = Get-PnPFeature @c -Identity $id -Scope Site
        if ($active -and (Get-MgProp $active 'DefinitionId')) { New-MgStep 'Feature' $name 'already active'; continue }
        if ($PSCmdlet.ShouldProcess($name, 'Enable site collection feature')) { Enable-PnPFeature @c -Identity $id -Scope Site }
        New-MgStep 'EnableFeature' $name "$id"
    }

    foreach ($col in @($Design.siteColumns)) {
        $existing = Invoke-MgQuiet { Get-PnPField @c -Identity $col.internalName -ErrorAction Stop }
        if ($existing) { New-MgStep 'Column' $col.internalName 'exists'; continue }
        $xml = ConvertTo-MgSiteColumnXml -Column $col
        if ($PSCmdlet.ShouldProcess($col.internalName, 'Add site column')) { $null = Add-PnPFieldFromXml @c -FieldXml $xml }
        New-MgStep 'AddColumn' $col.internalName $col.type
    }

    foreach ($ct in @($Design.contentTypes)) {
        $existing = Invoke-MgQuiet { Get-PnPContentType @c -Identity $ct.id -Includes FieldLinks -ErrorAction Stop }
        if (-not $existing) {
            if ($PSCmdlet.ShouldProcess($ct.name, 'Add content type')) {
                $null = Add-PnPContentType @c -Name $ct.name -ContentTypeId $ct.id -Group 'Contoso Purchasing' -Description (Get-MgProp $ct 'description' '')
            }
            New-MgStep 'AddContentType' $ct.name $ct.id
        }
        $links = @(); if ($existing) { $links = @($existing.FieldLinks | ForEach-Object { $_.Name }) }
        foreach ($fl in @(Get-MgProp $ct 'fields' @())) {
            if ($fl.name -in $links) { continue }
            $req = [bool](Get-MgProp $fl 'required' $false)
            if ($PSCmdlet.ShouldProcess("$($ct.name).$($fl.name)", 'Add field to content type')) {
                Add-PnPFieldToContentType @c -Field $fl.name -ContentType $ct.name -Required:$req
            }
            New-MgStep 'AddFieldLink' $ct.name "$($fl.name)$(if ($req) { ' (required)' })"
        }
        $ds = Get-MgProp $ct 'documentSet'
        if ($ds) {
            if ($PSCmdlet.ShouldProcess($ct.name, 'Allow content types in document set')) {
                Add-PnPContentTypeToDocumentSet @c -ContentType @($ds.allowedContentTypes) -DocumentSet $ct.name
            }
            New-MgStep 'DocSetAllowed' $ct.name (@($ds.allowedContentTypes) -join ', ')
            foreach ($s in @(Get-MgProp $ds 'sharedFields' @())) {
                if ($PSCmdlet.ShouldProcess("$($ct.name).$s", 'Share field')) { Set-PnPDocumentSetField @c -DocumentSet $ct.name -Field $s -SetSharedField }
                New-MgStep 'DocSetShared' $ct.name $s
            }
        }
    }

    foreach ($lib in @($Design.libraries)) {
        $list = Get-PnPList @c -Identity $lib.title
        if (-not $list) {
            if ($PSCmdlet.ShouldProcess($lib.title, 'Create library')) {
                $null = New-PnPList @c -Title $lib.title -Template DocumentLibrary -Url $lib.url -EnableContentTypes
            }
            New-MgStep 'CreateLibrary' $lib.title $lib.url
        }
        if ($PSCmdlet.ShouldProcess($lib.title, 'Set check-out and versioning')) {
            Set-PnPList @c -Identity $lib.title -EnableContentTypes $true -ForceCheckout ([bool](Get-MgProp $lib 'requireCheckout' $false)) -EnableVersioning $true
        }
        New-MgStep 'SetLibrary' $lib.title "requireCheckout=$([bool](Get-MgProp $lib 'requireCheckout' $false))"
        $have = @(); if ($list) { $have = @(Get-PnPContentType @c -List $lib.title | ForEach-Object { $_.Name }) }
        foreach ($n in @($lib.contentTypes)) {
            $isDefault = $n -eq (Get-MgProp $lib 'defaultContentType')
            if ($n -in $have) {
                if ($isDefault) {
                    if ($PSCmdlet.ShouldProcess($lib.title, "Default content type $n")) { Set-PnPDefaultContentTypeToList @c -List $lib.title -ContentType $n }
                    New-MgStep 'SetDefaultCT' $lib.title $n
                }
                continue
            }
            if ($PSCmdlet.ShouldProcess($lib.title, "Add content type $n")) { Add-PnPContentTypeToList @c -List $lib.title -ContentType $n -DefaultContentType:$isDefault }
            New-MgStep 'AddListCT' $lib.title "$n$(if ($isDefault) { ' (default)' })"
        }
        if ((Get-MgProp $lib 'removeDocumentContentType' $false) -and ((-not $list) -or 'Document' -in $have)) {
            if ($PSCmdlet.ShouldProcess($lib.title, 'Remove content type Document')) { Remove-PnPContentTypeFromList @c -List $lib.title -ContentType 'Document' }
            New-MgStep 'RemoveListCT' $lib.title 'Document'
        }
        foreach ($d in @(Get-MgProp $lib 'defaultValues' @())) {
            $folderArgs = @{}; $fd = Get-MgProp $d 'folder'; if ($fd) { $folderArgs.Folder = $fd }
            if ($PSCmdlet.ShouldProcess($lib.title, "Default $($d.field)")) { Set-PnPDefaultColumnValues @c -List $lib.title -Field $d.field -Value $d.value @folderArgs }
            New-MgStep 'DefaultValue' $lib.title "$($d.field) = $($d.value)"
        }
    }
}

function Invoke-MgFiling {
    <#
    .SYNOPSIS  Uploads files the filing plan resolved: one document set per folder value, then each file with its
               content type and metadata. Incomplete files are skipped unless -IncludeIncomplete; unmatched and
               invalid files are always skipped. Existing files are skipped.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)]$Plan, [Parameter(Mandatory)]$Design, [Parameter(Mandatory)][string]$Path,
        [switch]$IncludeIncomplete, $Connection
    )
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $lib = @($Design.libraries) | Where-Object title -eq $Plan.library | Select-Object -First 1
    $files = @(Get-ChildItem -LiteralPath $Path -File | Sort-Object Name)
    $resolved = @(Resolve-MgFilingPlan -Plan $Plan -Design $Design -FileName $files.Name)
    $sets = @{}
    foreach ($r in $resolved) {
        $ok = $r.Status -eq 'Ready' -or ($IncludeIncomplete -and $r.Status -eq 'Incomplete')
        if (-not $ok) { New-MgStep "Skip$($r.Status)" $r.FileName $r.Problem; continue }

        $folderUrl = $lib.url
        if ($r.Folder) {
            $folderUrl = "$($lib.url)/$($r.Folder)"
            if (-not $sets.ContainsKey($r.Folder)) {
                $sets[$r.Folder] = $true
                $exists = Invoke-MgQuiet { Get-PnPFolder @c -Url $folderUrl -ErrorAction Stop }
                if (-not $exists) {
                    if ($PSCmdlet.ShouldProcess($folderUrl, 'Create document set')) {
                        $null = Add-PnPDocumentSet @c -List $lib.title -Name $r.Folder -ContentType $Plan.folderContentType
                        $item = Get-PnPFolder @c -Url $folderUrl -AsListItem
                        $setValues = @{}; foreach ($m in [regex]::Matches(($Plan.rules | Where-Object name -eq $r.Rule).folder, '\{(\w+)\}')) { $setValues[$m.Groups[1].Value] = $r.Values[$m.Groups[1].Value] }
                        $null = Set-PnPListItem @c -List $lib.title -Identity $item.Id -Values $setValues
                    }
                    New-MgStep 'AddDocumentSet' $r.Folder $Plan.folderContentType
                }
            }
        }
        $existing = Invoke-MgQuiet { Get-PnPFile @c -Url "$folderUrl/$($r.FileName)" -ErrorAction Stop }
        if ($existing) { New-MgStep 'SkipExists' $r.FileName $folderUrl; continue }
        $vals = @{}; foreach ($k in $r.Values.Keys) { $vals[$k] = $r.Values[$k] }
        if ($PSCmdlet.ShouldProcess($r.FileName, "Upload to $folderUrl as $($r.ContentType)")) {
            $null = Add-PnPFile @c -Path (Join-Path $Path $r.FileName) -Folder $folderUrl -ContentType $r.ContentType -Values $vals
        }
        New-MgStep $(if ($r.Status -eq 'Ready') { 'Upload' } else { 'UploadIncomplete' }) $r.FileName "$($r.ContentType) -> $($r.Folder)"
    }
}

function Get-MgLibraryAudit {
    <# .SYNOPSIS  Reads every item of the library and runs Test-MgDocumentItem on it. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Design, [Parameter(Mandatory)][string]$Library,
        [datetime]$Today = (Get-Date).Date, [int]$ExpiryWarningDays = 60, [int]$StaleCheckoutDays = 14, $Connection
    )
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $items = @(Get-PnPListItem @c -List $Library -PageSize 500 -IncludeContentType | ConvertFrom-MgListItem)
    if (-not $items) { return }
    Test-MgDocumentItem -Items $items -Design $Design -Library $Library -Today $Today -ExpiryWarningDays $ExpiryWarningDays -StaleCheckoutDays $StaleCheckoutDays
}

Export-ModuleMember -Function Import-MgJson, Get-MgFeatureId, New-MgContentTypeId, Test-MgContentTypeId, Get-MgEffectiveField,
    Test-MgDocDesign, Test-MgFilingPlan, Resolve-MgFilingPlan, ConvertTo-MgSiteColumnXml, ConvertFrom-MgListItem,
    Test-MgDocumentItem, Invoke-MgDocMgmtProvisioning, Invoke-MgFiling, Get-MgLibraryAudit
