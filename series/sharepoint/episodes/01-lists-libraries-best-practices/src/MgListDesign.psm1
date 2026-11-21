#Requires -Version 7.2
<#
.SYNOPSIS
    Lists & libraries as code: lint a list design against SharePoint limits, provision it idempotently with
    PnP PowerShell, and audit a live list with the same rules.

    Pure functions (no SharePoint needed): Import-MgListDesign, Test-MgListDesign, ConvertTo-MgFieldXml,
    ConvertTo-MgViewQuery, ConvertTo-MgListDesign, New-MgSampleRequest.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Invoke-MgListProvisioning, Get-MgListAudit.
#>

Set-StrictMode -Version Latest

# ---- Limits we lint against (SharePoint in Microsoft 365) -------------------------------------------------------
# Sources (see README "References"):
#   list view threshold 5,000 items per query; adding/removing an index is limited to lists under 20,000 items
#   12 lookup/person joins per query ("list view lookup threshold")
#   30 million items per list/library; can't break inheritance on a list with more than 100,000 items
#   unique permissions: supported 50,000 per list, recommended 5,000
#   version limits below 100 major versions aren't recommended (the UI doesn't allow them)
#   an indexed Lookup column can't be used to stay under the list view threshold
$script:Limits = [ordered]@{
    ListViewThreshold        = 5000
    IndexChangeMaxItems      = 20000
    LookupColumnsPerView     = 12
    MaxItems                 = 30000000
    BreakInheritanceMaxItems = 100000
    UniqueScopesRecommended  = 5000
    UniqueScopesSupported    = 50000
    MinMajorVersions         = 100
}

# Built-in fields that views commonly reference, with their types.
$script:BuiltInFields = @{
    Title = 'Text'; LinkTitle = 'Text'; LinkTitleNoMenu = 'Text'; ID = 'Counter'
    Created = 'DateTime'; Modified = 'DateTime'; Author = 'User'; Editor = 'User'
    FileLeafRef = 'File'; LinkFilename = 'File'; LinkFilenameNoMenu = 'File'; DocIcon = 'Computed'
    ContentType = 'Computed'; Attachments = 'Attachments'; FileSizeDisplay = 'Computed'
}

# Field types that cost a join in a view query.
$script:JoinTypes = @('Lookup', 'LookupMulti', 'User', 'UserMulti', 'TaxonomyFieldType', 'TaxonomyFieldTypeMulti')

function Get-MgLimits { [CmdletBinding()] param() [pscustomobject]$script:Limits }

function Import-MgListDesign {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -Depth 20
}

function Get-MgProp($Object, [string]$Name, $Default = $null) {
    # StrictMode-safe property read for objects coming from JSON or CSOM.
    if ($null -ne $Object -and $Object.PSObject.Properties[$Name]) { $Object.$Name } else { $Default }
}

function Get-MgFieldTypeMap($List) {
    $map = @{}
    foreach ($k in $script:BuiltInFields.Keys) { $map[$k] = $script:BuiltInFields[$k] }
    foreach ($f in @(Get-MgProp $List 'fields' @())) { $map[$f.internalName] = $f.type }
    $map
}

function New-MgFinding([string]$Rule, [string]$Severity, [string]$List, [string]$Target, [string]$Message) {
    [pscustomobject]@{ Rule = $Rule; Severity = $Severity; List = $List; Target = $Target; Message = $Message }
}

function Test-MgListDesign {
    <#
    .SYNOPSIS  Lints a design (from Import-MgListDesign or ConvertTo-MgListDesign). Returns one object per finding.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory, ValueFromPipeline)]$Design)
    process {
        $L = $script:Limits
        foreach ($list in @($Design.lists)) {
            $name = $list.title
            $items = [long](Get-MgProp $list 'expectedItems' 0)
            $isLibrary = (Get-MgProp $list 'template' 'GenericList') -eq 'DocumentLibrary'
            $fields = @(Get-MgProp $list 'fields' @())
            $types = Get-MgFieldTypeMap $list
            $byName = @{}; foreach ($f in $fields) { $byName[$f.internalName] = $f }

            if ($items -gt $L.MaxItems) {
                New-MgFinding 'LD001' 'Error' $name $name "Expected $items items; a list or library holds up to $($L.MaxItems)."
            }

            # Columns
            $seen = @{}
            foreach ($f in $fields) {
                $n = $f.internalName
                if ($seen.ContainsKey($n)) {
                    New-MgFinding 'LD002' 'Error' $name $n "Internal name '$n' is defined more than once."
                }
                $seen[$n] = $true
                if (-not (Get-MgProp $f 'builtIn' $false) -and $n -notmatch '^[A-Za-z][A-Za-z0-9]*$') {
                    $encoded = $n -replace ' ', '_x0020_'
                    New-MgFinding 'LD003' 'Warning' $name $n "Internal name '$n' isn't plain letters and digits; SharePoint encodes it (e.g. '$encoded') and every formatter, filter and API call must use that. Create the column with a clean name, then rename the display name."
                }
            }

            # Versioning
            $ver = Get-MgProp $list 'versioning'
            if (-not (Get-MgProp $ver 'enabled' $false)) {
                $sev = if ($isLibrary) { 'Error' } else { 'Warning' }
                New-MgFinding 'LD004' $sev $name $name 'Versioning is off: nobody can restore a previous version.'
            }
            elseif (-not (Get-MgProp $ver 'automatic' $false)) {
                $major = Get-MgProp $ver 'majorVersions'
                if ($null -ne $major -and [int]$major -lt $L.MinMajorVersions) {
                    New-MgFinding 'LD005' 'Warning' $name $name "Keeps only $major major versions; fewer than $($L.MinMajorVersions) isn't recommended and can cause inadvertent data loss."
                }
            }

            # Permissions
            if ((Get-MgProp $list 'breakInheritance' $false) -and $items -gt $L.BreakInheritanceMaxItems) {
                New-MgFinding 'LD006' 'Error' $name $name "Plans to break inheritance on a list with $items items; that isn't possible above $($L.BreakInheritanceMaxItems) items. Use a separate list or site instead."
            }
            $scopes = [long](Get-MgProp $list 'plannedUniqueScopes' 0)
            if ($scopes -gt $L.UniqueScopesSupported) {
                New-MgFinding 'LD007' 'Error' $name $name "$scopes unique permission scopes; the supported limit is $($L.UniqueScopesSupported)."
            }
            elseif ($scopes -gt $L.UniqueScopesRecommended) {
                New-MgFinding 'LD007' 'Warning' $name $name "$scopes unique permission scopes; the recommended limit is $($L.UniqueScopesRecommended)."
            }

            # Folders (house rule: metadata over folders; paths are limited to 400 characters)
            $depth = [int](Get-MgProp $list 'folderDepth' 0)
            if ($depth -gt 2) {
                New-MgFinding 'LD008' 'Warning' $name $name "Folders $depth levels deep. Prefer metadata columns and views; deep paths also eat into the 400-character path limit."
            }

            # Views
            foreach ($v in @(Get-MgProp $list 'views' @())) {
                $vt = "$name / $($v.title)"
                $vf = @(Get-MgProp $v 'fields' @())
                $filters = @(Get-MgProp $v 'filters' @())

                foreach ($fieldName in @($vf + @($filters | ForEach-Object { $_.field }))) {
                    if (-not $types.ContainsKey($fieldName)) {
                        New-MgFinding 'LD009' 'Error' $name $vt "View uses '$fieldName', which isn't a column of this list."
                    }
                }

                $joins = @($vf | Where-Object { $types.ContainsKey($_) -and $types[$_] -in $script:JoinTypes })
                if ($joins.Count -gt $L.LookupColumnsPerView) {
                    New-MgFinding 'LD010' 'Error' $name $vt "$($joins.Count) lookup/person columns (including Created By and Modified By); the limit is $($L.LookupColumnsPerView) per view."
                }

                $rows = Get-MgProp $v 'expectedRows'
                if ($null -ne $rows -and [long]$rows -gt $L.ListViewThreshold) {
                    New-MgFinding 'LD011' 'Error' $name $vt "Filter still returns about $rows items; a view query must stay at or under $($L.ListViewThreshold)."
                }

                if ($items -gt $L.ListViewThreshold) {
                    if ($filters.Count -eq 0) {
                        New-MgFinding 'LD012' 'Error' $name $vt "No filter on a list expected to hold $items items. Filter on an indexed column so the query stays under $($L.ListViewThreshold)."
                    }
                    else {
                        $first = $filters[0].field
                        $indexed = [bool](Get-MgProp $byName[$first] 'indexed' $false)
                        if (-not $indexed) {
                            New-MgFinding 'LD013' 'Error' $name $vt "First filter column '$first' isn't indexed. Index it while the list is small: adding or removing an index is limited to lists under $($L.IndexChangeMaxItems) items."
                        }
                        elseif ($types[$first] -in 'Lookup', 'LookupMulti') {
                            New-MgFinding 'LD014' 'Error' $name $vt "First filter column '$first' is an indexed Lookup. That doesn't keep a view under the threshold; filter first on another indexed column."
                        }
                    }
                }
            }
        }
    }
}

function ConvertTo-MgXmlText([string]$Value) { [System.Security.SecurityElement]::Escape($Value) }

function ConvertTo-MgFieldXml {
    <#
    .SYNOPSIS  Field schema XML for Add-PnPFieldFromXml. Name and StaticName are the clean internal name.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$Field,
        [string]$LookupListId
    )
    $n = ConvertTo-MgXmlText $Field.internalName
    $display = ConvertTo-MgXmlText (Get-MgProp $Field 'displayName' $Field.internalName)
    $req = if (Get-MgProp $Field 'required' $false) { 'TRUE' } else { 'FALSE' }
    $idx = if (Get-MgProp $Field 'indexed' $false) { ' Indexed="TRUE"' } else { '' }
    $common = "Name=`"$n`" StaticName=`"$n`" DisplayName=`"$display`" Required=`"$req`"$idx"
    $inner = ''
    switch ($Field.type) {
        'Text'     { $attrs = "Type=`"Text`" MaxLength=`"255`"" }
        'Note'     { $attrs = "Type=`"Note`" NumLines=`"6`" RichText=`"FALSE`"" }
        'Number'   { $attrs = "Type=`"Number`"" }
        'Currency' { $attrs = "Type=`"Currency`" Decimals=`"2`"" }
        'Boolean'  { $attrs = "Type=`"Boolean`""; $inner = '<Default>0</Default>' }
        'DateTime' {
            $fmt = if (Get-MgProp $Field 'dateOnly' $false) { 'DateOnly' } else { 'DateTime' }
            $attrs = "Type=`"DateTime`" Format=`"$fmt`""
        }
        { $_ -in 'Choice', 'MultiChoice' } {
            $attrs = if ($_ -eq 'Choice') { "Type=`"Choice`" Format=`"Dropdown`"" } else { "Type=`"MultiChoice`"" }
            $choices = (@($Field.choices) | ForEach-Object { "<CHOICE>$(ConvertTo-MgXmlText $_)</CHOICE>" }) -join ''
            $inner = "<CHOICES>$choices</CHOICES>"
            $def = Get-MgProp $Field 'default'
            if ($def) { $inner += "<Default>$(ConvertTo-MgXmlText $def)</Default>" }
        }
        'User'      { $attrs = "Type=`"User`" UserSelectionMode=`"PeopleOnly`"" }
        'UserMulti' { $attrs = "Type=`"UserMulti`" UserSelectionMode=`"PeopleOnly`" Mult=`"TRUE`"" }
        { $_ -in 'Lookup', 'LookupMulti' } {
            if (-not $LookupListId) { throw "Lookup column '$($Field.internalName)' needs -LookupListId." }
            $mult = if ($_ -eq 'LookupMulti') { ' Mult="TRUE"' } else { '' }
            $attrs = "Type=`"$_`" List=`"{$LookupListId}`" ShowField=`"Title`"$mult"
        }
        default { throw "Unsupported field type '$($Field.type)' for '$($Field.internalName)'." }
    }
    if ($inner) { "<Field $attrs $common>$inner</Field>" } else { "<Field $attrs $common />" }
}

function ConvertTo-MgCamlValue([string]$FieldType, [string]$Value) {
    if ($Value -eq '[Me]') { return "<Value Type='Integer'><UserID Type='Integer' /></Value>" }
    if ($Value -match '^\[Today(?<off>[+-]\d+)?\]$') {
        $today = if ($Matches['off']) { "<Today OffsetDays='$([int]$Matches['off'])' />" } else { '<Today />' }
        return "<Value Type='DateTime'>$today</Value>"
    }
    $camlType = switch ($FieldType) {
        { $_ -in 'Text', 'Note', 'File' } { 'Text' }
        'Choice' { 'Choice' } 'MultiChoice' { 'MultiChoice' }
        'DateTime' { 'DateTime' } 'Number' { 'Number' } 'Currency' { 'Currency' }
        'Counter' { 'Counter' } 'Boolean' { 'Boolean' }
        { $_ -in 'User', 'UserMulti' } { 'User' }
        { $_ -in 'Lookup', 'LookupMulti' } { 'Lookup' }
        default { 'Text' }
    }
    "<Value Type='$camlType'>$(ConvertTo-MgXmlText $Value)</Value>"
}

function ConvertTo-MgViewQuery {
    <#
    .SYNOPSIS  CAML for Add-PnPView -Query: <Where> (filters joined with And, first filter first) + <OrderBy>.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$View, [hashtable]$FieldTypes = @{})
    $ops = 'Eq', 'Neq', 'Lt', 'Leq', 'Gt', 'Geq', 'IsNull', 'IsNotNull', 'Contains', 'BeginsWith'
    $parts = foreach ($f in @(Get-MgProp $View 'filters' @())) {
        if ($f.op -notin $ops) { throw "Unsupported operator '$($f.op)' in view '$($View.title)'." }
        $ref = "<FieldRef Name='$(ConvertTo-MgXmlText $f.field)' />"
        if ($f.op -in 'IsNull', 'IsNotNull') { "<$($f.op)>$ref</$($f.op)>" }
        else {
            $t = if ($FieldTypes.ContainsKey($f.field)) { $FieldTypes[$f.field] } else { 'Text' }
            "<$($f.op)>$ref$(ConvertTo-MgCamlValue $t ([string]$f.value))</$($f.op)>"
        }
    }
    $where = ''
    if (@($parts).Count -gt 0) {
        $expr = @($parts)[0]
        foreach ($p in @($parts | Select-Object -Skip 1)) { $expr = "<And>$expr$p</And>" }
        $where = "<Where>$expr</Where>"
    }
    $order = ''
    $ob = Get-MgProp $View 'orderBy'
    if ($ob) {
        $asc = if (Get-MgProp $ob 'ascending' $true) { 'TRUE' } else { 'FALSE' }
        $order = "<OrderBy><FieldRef Name='$(ConvertTo-MgXmlText $ob.field)' Ascending='$asc' /></OrderBy>"
    }
    "$where$order"
}

function Get-MgCamlFilters([string]$ViewQuery) {
    # Comparison elements under <Where>, in document order (= the order the filters were written).
    if ([string]::IsNullOrWhiteSpace($ViewQuery)) { return @() }
    [xml]$doc = "<Query>$ViewQuery</Query>"
    $where = $doc.Query.SelectSingleNode('Where')
    if (-not $where) { return @() }
    foreach ($node in $where.SelectNodes('.//*[FieldRef]')) {
        if ($node.LocalName -in 'And', 'Or') { continue }
        [pscustomobject]@{ field = $node.SelectSingleNode('FieldRef').GetAttribute('Name'); op = $node.LocalName }
    }
}

function ConvertTo-MgListDesign {
    <#
    .SYNOPSIS  Maps a live list (CSOM objects from PnP, or look-alike objects in tests) to the design shape,
               so Test-MgListDesign can lint what is actually in the tenant.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]$List,
        [Parameter(Mandatory)][object[]]$Fields,
        [Parameter(Mandatory)][object[]]$Views,
        [long]$ExpectedItems = 0,
        [long]$UniqueScopes = 0
    )
    # Every column goes in (views may reference hidden or base-type columns); built-ins are flagged so the
    # naming rule only applies to columns someone created.
    $designFields = foreach ($f in $Fields) {
        $builtIn = ((Get-MgProp $f 'FromBaseType' $false) -or (Get-MgProp $f 'Hidden' $false)) -and $f.InternalName -ne 'Title'
        [pscustomobject]@{
            internalName = $f.InternalName; displayName = $f.Title; type = $f.TypeAsString
            indexed = [bool](Get-MgProp $f 'Indexed' $false); builtIn = [bool]$builtIn
        }
    }
    $designViews = foreach ($v in $Views | Where-Object { -not (Get-MgProp $_ 'Hidden' $false) }) {
        [pscustomobject]@{
            title   = $v.Title
            fields  = @($v.ViewFields)
            filters = @(Get-MgCamlFilters $v.ViewQuery)
            rowLimit = $v.RowLimit
        }
    }
    $isLibrary = [int](Get-MgProp $List 'BaseTemplate' 100) -eq 101
    $items = [math]::Max([long](Get-MgProp $List 'ItemCount' 0), $ExpectedItems)
    [pscustomobject]@{
        lists = @([pscustomobject]@{
                title               = $List.Title
                template            = if ($isLibrary) { 'DocumentLibrary' } else { 'GenericList' }
                expectedItems       = $items
                versioning          = [pscustomobject]@{
                    enabled       = [bool](Get-MgProp $List 'EnableVersioning' $false)
                    majorVersions = Get-MgProp $List 'MajorVersionLimit'
                }
                breakInheritance    = [bool](Get-MgProp $List 'HasUniqueRoleAssignments' $false)
                plannedUniqueScopes = $UniqueScopes
                fields              = @($designFields)
                views               = @($designViews)
            })
    }
}

function New-MgSampleRequest {
    <#
    .SYNOPSIS  Deterministic fictional request rows (values hashtables for Add-PnPListItem).
    #>
    [CmdletBinding()]
    param(
        [int]$Count = 20,
        [Parameter(Mandatory)][string]$RequesterEmail,
        [datetime]$Today = (Get-Date).Date,
        [int]$Seed = 42
    )
    $rnd = [System.Random]::new($Seed)
    $items = 'Laptop', 'Monitor', 'Conference tickets', 'Software licence', 'Office chairs', 'Training course', 'Printer toner', 'Headsets'
    $statuses = 'New', 'Approved', 'Ordered', 'Closed', 'Rejected'
    $depts = 'Finance', 'IT', 'Marketing', 'Operations', 'People'
    for ($i = 1; $i -le $Count; $i++) {
        @{
            Title         = '{0} #{1:000}' -f $items[$rnd.Next($items.Count)], $i
            RequestStatus = $statuses[$rnd.Next($statuses.Count)]
            Requester     = $RequesterEmail
            Department    = $depts[$rnd.Next($depts.Count)]
            Amount        = [math]::Round(50 + $rnd.NextDouble() * 24950, 2)
            DueDate       = $Today.AddDays($rnd.Next(-10, 30)).ToString('yyyy-MM-dd')
        }
    }
}

# ---- Tenant functions (PnP.PowerShell) ---------------------------------------------------------------------------

function Invoke-MgListProvisioning {
    <#
    .SYNOPSIS  Creates or updates lists, columns, indexes, versioning and views from a design. Safe to re-run.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Design)

    foreach ($l in @($Design.lists)) {
        $title = $l.title
        $template = Get-MgProp $l 'template' 'GenericList'
        $types = Get-MgFieldTypeMap $l

        $list = Get-PnPList -Identity $title -ErrorAction SilentlyContinue
        if (-not $list) {
            if ($PSCmdlet.ShouldProcess($title, "Create $template")) {
                $list = New-PnPList -Title $title -Template $template -Url $l.url -OnQuickLaunch
            }
            [pscustomobject]@{ Action = 'CreateList'; Target = $title; Detail = $template }
        }

        $ver = Get-MgProp $l 'versioning'
        if (Get-MgProp $ver 'enabled' $false) {
            if ((Get-MgProp $ver 'automatic' $false) -and $template -eq 'DocumentLibrary') {
                if ($PSCmdlet.ShouldProcess($title, 'Versioning: automatic version history limits')) {
                    Set-PnPList -Identity $title -EnableVersioning $true -EnableAutoExpirationVersionTrim $true | Out-Null
                }
                [pscustomobject]@{ Action = 'SetVersioning'; Target = $title; Detail = 'automatic' }
            }
            else {
                $major = [uint32](Get-MgProp $ver 'majorVersions' 500)
                if ($PSCmdlet.ShouldProcess($title, "Versioning: $major major versions")) {
                    Set-PnPList -Identity $title -EnableVersioning $true -MajorVersions $major | Out-Null
                }
                [pscustomobject]@{ Action = 'SetVersioning'; Target = $title; Detail = "$major major versions" }
            }
        }

        foreach ($f in @($l.fields)) {
            # Some PnP versions throw for a missing field instead of returning nothing.
            $existing = try { Get-PnPField -List $title -Identity $f.internalName -ErrorAction SilentlyContinue } catch { $null }
            $wantIndex = [bool](Get-MgProp $f 'indexed' $false)
            if (-not $existing) {
                $lookupId = $null
                if ($f.type -in 'Lookup', 'LookupMulti') {
                    $lookupId = (Get-PnPList -Identity $f.lookupList -ErrorAction Stop).Id.ToString()
                }
                $xml = ConvertTo-MgFieldXml -Field $f -LookupListId $lookupId
                if ($PSCmdlet.ShouldProcess("$title/$($f.internalName)", 'Add column')) {
                    Add-PnPFieldFromXml -List $title -FieldXml $xml | Out-Null
                }
                [pscustomobject]@{ Action = 'AddField'; Target = "$title/$($f.internalName)"; Detail = $f.type + $(if ($wantIndex) { ', indexed' }) }
            }
            elseif ($wantIndex -and -not $existing.Indexed) {
                if ($PSCmdlet.ShouldProcess("$title/$($f.internalName)", 'Index column')) {
                    Set-PnPField -List $title -Identity $f.internalName -Values @{ Indexed = $true } | Out-Null
                }
                [pscustomobject]@{ Action = 'IndexField'; Target = "$title/$($f.internalName)"; Detail = 'indexed' }
            }
        }

        foreach ($v in @(Get-MgProp $l 'views' @())) {
            $query = ConvertTo-MgViewQuery -View $v -FieldTypes $types
            $rowLimit = [uint32](Get-MgProp $v 'rowLimit' 30)
            $isDefault = [bool](Get-MgProp $v 'default' $false)
            $existing = try { Get-PnPView -List $title -Identity $v.title -ErrorAction SilentlyContinue } catch { $null }
            if (-not $existing) {
                if ($PSCmdlet.ShouldProcess("$title/$($v.title)", 'Add view')) {
                    Add-PnPView -List $title -Title $v.title -Fields $v.fields -Query $query -RowLimit $rowLimit -Paged -SetAsDefault:$isDefault | Out-Null
                }
                [pscustomobject]@{ Action = 'AddView'; Target = "$title/$($v.title)"; Detail = $query }
            }
            else {
                if ($PSCmdlet.ShouldProcess("$title/$($v.title)", 'Update view')) {
                    Set-PnPView -List $title -Identity $v.title -Fields $v.fields -Values @{
                        ViewQuery = $query; RowLimit = $rowLimit; Paged = $true; DefaultView = $isDefault
                    } | Out-Null
                }
                [pscustomobject]@{ Action = 'UpdateView'; Target = "$title/$($v.title)"; Detail = $query }
            }
        }

        # SharePoint creates an unfiltered default view ("All Items" / "All Documents"). On a list designed to grow
        # past the threshold, remove it once one of our filtered views is the default.
        foreach ($name in @(Get-MgProp $l 'removeViews' @())) {
            $existing = try { Get-PnPView -List $title -Identity $name -ErrorAction SilentlyContinue } catch { $null }
            if ($existing) {
                if ($PSCmdlet.ShouldProcess("$title/$name", 'Remove view')) {
                    Remove-PnPView -List $title -Identity $name -Force | Out-Null
                }
                [pscustomobject]@{ Action = 'RemoveView'; Target = "$title/$name"; Detail = 'unfiltered default view' }
            }
        }
    }
}

function Get-MgListAudit {
    <#
    .SYNOPSIS  Reads a live list and lints it with the same rules. -ExpectedItems lints for the size it will grow to.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$ListTitle, [long]$ExpectedItems = 0)
    $list = Get-PnPList -Identity $ListTitle -Includes HasUniqueRoleAssignments, MajorVersionLimit, EnableVersioning -ErrorAction Stop
    $fields = @(Get-PnPField -List $ListTitle)
    $views = @(Get-PnPView -List $ListTitle -Includes ViewFields, ViewQuery, RowLimit, Hidden)
    $design = ConvertTo-MgListDesign -List $list -Fields $fields -Views $views -ExpectedItems $ExpectedItems
    [pscustomobject]@{ Design = $design; Findings = @(Test-MgListDesign -Design $design) }
}

Export-ModuleMember -Function Get-MgLimits, Import-MgListDesign, Test-MgListDesign, ConvertTo-MgFieldXml,
    ConvertTo-MgViewQuery, ConvertTo-MgListDesign, New-MgSampleRequest, Invoke-MgListProvisioning, Get-MgListAudit
