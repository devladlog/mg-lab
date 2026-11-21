#Requires -Version 7.2
<#
.SYNOPSIS
    Search and metadata as code for the Contoso Purchasing site: a managed metadata term set with fixed IDs, a
    Category column on the episode 4 content types, a search plan (which site columns go into which refinable
    managed properties, under which alias), a KQL linter, and search tests that run real queries and check results.

    Pure functions (no SharePoint needed): Import-MgJson, Get-MgAutoPropertyName, Test-MgTermSet, Resolve-MgTermPath,
    Test-MgSearchPlan, Get-MgManagedPropertyInfo, ConvertTo-MgKql, Test-MgKql, Test-MgSearchMapping,
    Test-MgSearchResult.
    Tenant functions (PnP.PowerShell, after Connect-PnPOnline): Invoke-MgTaxonomyProvisioning,
    Invoke-MgCategoryColumn, Invoke-MgCategoryTagging, Get-MgSiteSearchMapping, Invoke-MgSearchTest.
#>

Set-StrictMode -Version Latest

# ---- What Learn documents (see README "References") -------------------------------------------------------------
#   SharePoint in Microsoft 365: new managed properties can only be Text or Yes/No and can't be refinable or
#   sortable; refinable managed properties can't be created: reuse the default unused ones and rename them with an
#   alias. Ranges (type, count, refinable?):
$script:UnusedRanges = @(
    @{ Prefix = 'RefinableStringWbOffFirst'; Max = 49; Type = 'Text'; Refine = $true }
    @{ Prefix = 'RefinableStringWbOff'; Max = 49; Type = 'Text'; Refine = $true }
    @{ Prefix = 'RefinableStringFirst'; Max = 39; Type = 'Text'; Refine = $true }
    @{ Prefix = 'RefinableStringLn'; Max = 9; Type = 'Text'; Refine = $true }
    @{ Prefix = 'RefinableString'; Max = 219; Type = 'Text'; Refine = $true }
    @{ Prefix = 'RefinableDateInvariant'; Max = 1; Type = 'DateTime'; Refine = $true }
    @{ Prefix = 'RefinableDateSingle'; Max = 4; Type = 'DateTime'; Refine = $true }
    @{ Prefix = 'RefinableDate'; Max = 19; Type = 'DateTime'; Refine = $true }
    @{ Prefix = 'RefinableDecimal'; Max = 9; Type = 'Decimal'; Refine = $true }
    @{ Prefix = 'RefinableDouble'; Max = 9; Type = 'Double'; Refine = $true }
    @{ Prefix = 'RefinableInt'; Max = 49; Type = 'Integer'; Refine = $true }
    @{ Prefix = 'Date'; Max = 9; Type = 'DateTime'; Refine = $false }
    @{ Prefix = 'Decimal'; Max = 9; Type = 'Decimal'; Refine = $false }
    @{ Prefix = 'Double'; Max = 9; Type = 'Double'; Refine = $false }
    @{ Prefix = 'Int'; Max = 49; Type = 'Integer'; Refine = $false }
)
#   Built-in managed properties used in this episode (name -> type), from the Learn property overviews.
$script:BuiltIn = [ordered]@{
    Author = 'Text'; contentclass = 'Text'; ContentTypeId = 'Text'; Created = 'DateTime'; FileExtension = 'Text'
    Filename = 'Text'; FileType = 'Text'; IsDocument = 'YesNo'; LastModifiedTime = 'DateTime'; Path = 'Text'
    Size = 'Integer'; Title = 'Text'; DepartmentId = 'Text'; RelatedHubSites = 'Text'; IsHubSite = 'YesNo'
}
#   Automatically created properties for site columns (SharePoint Server reference): crawled ows_q_<CODE>_<Name>
#   (ows_r_ for multiple lines of text and publishing HTML, ows_taxId_ for managed metadata); managed <Name>OWS<CODE>
#   (owstaxId<Name> for managed metadata). All automatically created managed properties are of type Text.
$script:ColumnCodes = @{
    Text = @('q', 'TEXT'); Note = @('r', 'MTXT'); Choice = @('q', 'CHCS'); MultiChoice = @('q', 'CHCM'); Number = @('q', 'NMBR')
    Currency = @('q', 'CURR'); DateTime = @('q', 'DATE'); Boolean = @('q', 'BOOL'); User = @('q', 'USER'); URL = @('q', 'URLH')
    Integer = @('q', 'INTG'); Guid = @('q', 'GUID')
}
#   Which unused managed property type can hold which column type.
$script:Compatible = @{
    Text = 'Text'; Note = 'Text'; Choice = 'Text'; MultiChoice = 'Text'; User = 'Text'; URL = 'Text'; TaxonomyFieldType = 'Text'
    DateTime = 'DateTime'; Number = 'Decimal|Double|Integer'; Currency = 'Decimal|Double'; Integer = 'Integer'; Boolean = 'Integer|Text'
}
#   KQL: operators are uppercase; 2,048 characters in the search box, 4,096 by default from code; a property
#   restriction is limited to 2,048 characters; < > <= >= .. only for DateTime, Integer, Decimal and Double.
$script:KqlMaxProgrammatic = 4096
$script:KqlMaxFrontEnd = 2048
$script:KqlMaxRestriction = 2048
$script:RangeTypes = @('DateTime', 'Integer', 'Decimal', 'Double')
$script:DateKeywords = @('today', 'yesterday', 'this week', 'this month', 'last month', 'this year', 'last year')

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

# ---- Automatically created properties -------------------------------------------------------------------------------

function Get-MgAutoPropertyName {
    <#
    .SYNOPSIS  The crawled and managed property names search creates for a site column (documented convention).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string]$Type)
    $crawlName = $Name -replace ' ', ''
    $managedName = $Name -replace '[^A-Za-z0-9]', ''
    if ($Type -eq 'TaxonomyFieldType') {
        return [pscustomobject]@{ Crawled = "ows_taxId_$crawlName"; Managed = "owstaxId$managedName"; ManagedType = 'Text' }
    }
    $code = $script:ColumnCodes[$Type]
    if (-not $code) { throw "No automatically created property for column type '$Type'." }
    [pscustomobject]@{ Crawled = "ows_$($code[0])_$($code[1])_$crawlName"; Managed = "${managedName}OWS$($code[1])"; ManagedType = 'Text' }
}

function Get-MgManagedPropertyInfo {
    <#
    .SYNOPSIS  Type and refinability of a default unused managed property, or $null if the name isn't one.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Name)
    foreach ($r in $script:UnusedRanges) {
        if ($Name -match "^$($r.Prefix)(\d{2,3})$") {
            $n = [int]$Matches[1]
            if ($Matches[1].Length -eq 3 -and $n -lt 100) { return $null }
            if ($n -le $r.Max) { return [pscustomobject]@{ Name = $Name; Type = $r.Type; Refinable = $r.Refine; Range = "$($r.Prefix)00-$($r.Prefix)$('{0:D2}' -f $r.Max)" } }
            return [pscustomobject]@{ Name = $Name; Type = $r.Type; Refinable = $r.Refine; Range = "$($r.Prefix)00-$($r.Prefix)$('{0:D2}' -f $r.Max)"; OutOfRange = $true }
        }
    }
    $null
}

# ---- Term set ------------------------------------------------------------------------------------------------------

function Get-MgTermList($Terms, [string]$ParentPath = '', [string]$ParentId = $null, [int]$Level = 1) {
    foreach ($t in @($Terms | Where-Object { $null -ne $_ })) {
        $path = if ($ParentPath) { "$ParentPath|$($t.name)" } else { $t.name }
        [pscustomobject]@{ Name = $t.name; Id = $t.id; Path = $path; ParentId = $ParentId; ParentPath = $ParentPath; Level = $Level }
        Get-MgTermList (Get-MgProp $t 'children' @()) $path $t.id ($Level + 1)
    }
}

function Test-MgTermSet {
    <#
    .SYNOPSIS  Checks a term set definition (TX001-TX003): GUIDs, unique labels per level, empty labels.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$TermSet)
    $ids = @{}
    $all = @(Get-MgTermList $TermSet.terms)
    $nodes = @(
        [pscustomobject]@{ Name = $TermSet.group.name; Id = $TermSet.group.id; Path = "group '$($TermSet.group.name)'" }
        [pscustomobject]@{ Name = $TermSet.termSet.name; Id = $TermSet.termSet.id; Path = "term set '$($TermSet.termSet.name)'" }
    ) + $all
    foreach ($n in $nodes) {
        $g = [guid]::Empty
        if (-not [guid]::TryParse("$($n.Id)", [ref]$g) -or $g -eq [guid]::Empty) {
            New-MgFinding 'TX001' 'Error' $n.Path "'$($n.Id)' isn't a GUID: fixed IDs make the terms the same in every tenant and usable in queries."
        }
        elseif ($ids.ContainsKey("$g")) { New-MgFinding 'TX001' 'Error' $n.Path "ID $g is also used by $($ids["$g"])." }
        else { $ids["$g"] = $n.Path }
        if ([string]::IsNullOrWhiteSpace($n.Name)) { New-MgFinding 'TX003' 'Error' $n.Path 'Empty label.' }
    }
    foreach ($level in $all | Group-Object ParentPath) {
        foreach ($dup in $level.Group | Group-Object { $_.Name.Trim().ToLowerInvariant() } | Where-Object Count -gt 1) {
            New-MgFinding 'TX002' 'Error' "term '$($dup.Group[0].Path)'" "Label '$($dup.Group[0].Name)' appears $($dup.Count) times at the same level."
        }
    }
}

function Resolve-MgTermPath {
    <#
    .SYNOPSIS  'Facilities|Cleaning' -> the term (Name, Id, Path) or $null.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$TermSet, [Parameter(Mandatory)][string]$Path)
    @(Get-MgTermList $TermSet.terms | Where-Object { $_.Path -eq $Path }) | Select-Object -First 1
}

# ---- Search plan ---------------------------------------------------------------------------------------------------

function Get-MgCrawledCandidates($Column) {
    $auto = Get-MgAutoPropertyName -Name $Column.internalName -Type $Column.type
    @($auto.Crawled, "ows_$($Column.internalName)")
}

function Test-MgSearchPlan {
    <#
    .SYNOPSIS  Checks the search plan (SP001-SP007) and, with -TermSet, the category column and tagging (TX004-TX005).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, $TermSet)
    $columns = @{}
    foreach ($c in @($Plan.columns)) { $columns[$c.internalName] = $c }
    $used = @{}
    $aliases = @{}
    $builtInNames = @($script:BuiltIn.Keys | ForEach-Object { $_.ToLowerInvariant() })
    foreach ($m in @($Plan.mappings)) {
        $target = "mapping '$($m.managedProperty)'"
        $info = Get-MgManagedPropertyInfo -Name $m.managedProperty
        if (-not $info) {
            New-MgFinding 'SP001' 'Error' $target "'$($m.managedProperty)' isn't a default unused managed property. In SharePoint in Microsoft 365 a new managed property can only be Text or Yes/No and can't be refinable or sortable: reuse RefinableString00-219, RefinableDate00-19, ..."
            continue
        }
        if (Get-MgProp $info 'OutOfRange') {
            New-MgFinding 'SP001' 'Error' $target "'$($m.managedProperty)' doesn't exist: the range is $($info.Range)."
            continue
        }
        if ($used.ContainsKey($m.managedProperty)) {
            New-MgFinding 'SP003' 'Error' $target "Also used for column '$($used[$m.managedProperty])': one managed property, one meaning."
        }
        else { $used[$m.managedProperty] = $m.column }
        $col = $columns[$m.column]
        if (-not $col) { New-MgFinding 'SP002' 'Error' $target "Column '$($m.column)' isn't in the plan's columns."; continue }
        if ($info.Type -notmatch "^($($script:Compatible[$col.type]))$") {
            New-MgFinding 'SP002' 'Error' $target "Column '$($m.column)' is $($col.type) but $($m.managedProperty) is $($info.Type): $(if ($col.type -eq 'DateTime') { 'dates would compare as text' } else { 'values would not compare or sort correctly' })."
        }
        if ((Get-MgProp $m 'refine' $false) -and -not $info.Refinable) {
            New-MgFinding 'SP006' 'Warning' $target "$($m.managedProperty) can't refine or sort: use the Refinable range ($($info.Type))."
        }
        $alias = Get-MgProp $m 'alias'
        if ($alias) {
            if ($alias -notmatch '^[A-Za-z][A-Za-z0-9]*$') {
                New-MgFinding 'SP004' 'Warning' $target "Alias '$alias': use only letters and digits; other characters act as query operators."
            }
            $l = $alias.ToLowerInvariant()
            if ($l -in $builtInNames -or (Get-MgManagedPropertyInfo -Name $alias) -or $l -eq (Get-MgAutoPropertyName -Name $col.internalName -Type $col.type).Managed.ToLowerInvariant()) {
                New-MgFinding 'SP005' 'Error' $target "Alias '$alias' is the name of an existing managed property: aliased properties take precedence and can break Microsoft 365 experiences."
            }
            if ($aliases.ContainsKey($l)) { New-MgFinding 'SP005' 'Error' $target "Alias '$alias' is also used for $($aliases[$l])." }
            else { $aliases[$l] = $m.managedProperty }
        }
        $candidates = Get-MgCrawledCandidates $col
        $crawled = Get-MgProp $m 'crawledProperty'
        if ($crawled -and $crawled -notin $candidates) {
            New-MgFinding 'SP007' 'Warning' $target "Crawled property '$crawled' doesn't match a $($col.type) column '$($col.internalName)' (expected $($candidates -join ' or '))."
        }
    }
    if ($TermSet) {
        $col = Get-MgProp $Plan 'categoryColumn'
        if ($col -and (Get-MgProp $col 'termSetPath') -ne "$($TermSet.group.name)|$($TermSet.termSet.name)") {
            New-MgFinding 'TX004' 'Error' 'categoryColumn' "Term set path '$($col.termSetPath)' isn't '$($TermSet.group.name)|$($TermSet.termSet.name)'."
        }
        if ($col -and -not (Get-MgProp $TermSet.termSet 'availableForTagging' $true)) {
            New-MgFinding 'TX005' 'Warning' 'categoryColumn' "The term set isn't available for tagging: people can't pick its terms."
        }
        foreach ($p in @((Get-MgProp $Plan 'supplierCategories' ([pscustomobject]@{})).PSObject.Properties)) {
            if (-not (Resolve-MgTermPath -TermSet $TermSet -Path $p.Value)) {
                New-MgFinding 'TX004' 'Error' "supplierCategories['$($p.Name)']" "'$($p.Value)' isn't a term of '$($TermSet.termSet.name)'."
            }
        }
    }
}

# ---- KQL -----------------------------------------------------------------------------------------------------------

function Get-MgQueryProperties {
    <#
    .SYNOPSIS  Every property name a query may use, with its type: built-ins, plan targets and aliases, auto properties.
    #>
    [CmdletBinding()]
    param($Plan)
    $p = [ordered]@{}
    foreach ($k in $script:BuiltIn.Keys) { $p[$k.ToLowerInvariant()] = $script:BuiltIn[$k] }
    if ($Plan) {
        foreach ($c in @($Plan.columns)) { $a = Get-MgAutoPropertyName -Name $c.internalName -Type $c.type; $p[$a.Managed.ToLowerInvariant()] = 'Text' }
        foreach ($m in @($Plan.mappings)) {
            $info = Get-MgManagedPropertyInfo -Name $m.managedProperty
            if (-not $info -or (Get-MgProp $info 'OutOfRange')) { continue }
            $p[$m.managedProperty.ToLowerInvariant()] = $info.Type
            if (Get-MgProp $m 'alias') { $p[$m.alias.ToLowerInvariant()] = $info.Type }
        }
    }
    $p
}

function ConvertTo-MgKql {
    <#
    .SYNOPSIS  Resolves tokens in a query template: {site}, {today}, {today+60d}, {today-30d}, {ct:Name}, {term:Path}, {termset}.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Template, $Plan, $TermSet, [string]$SiteUrl = 'https://contoso.sharepoint.com/sites/Purchasing',
        [datetime]$Today = (Get-Date).Date)
    [regex]::Replace($Template, '\{([^{}]+)\}', {
            param($m)
            $t = $m.Groups[1].Value
            switch -Regex ($t) {
                '^site$' { return $SiteUrl }
                '^today$' { return $Today.ToString('yyyy-MM-dd') }
                '^today([+-]\d+)d$' { return $Today.AddDays([int]$Matches[1]).ToString('yyyy-MM-dd') }
                '^ct:(.+)$' {
                    $id = Get-MgProp (Get-MgProp $Plan 'contentTypes') $Matches[1]
                    if (-not $id) { throw "Unknown content type '$($Matches[1])' in {$t}." }
                    return $id
                }
                '^termset$' { return "$($TermSet.termSet.id)" }
                '^term:(.+)$' {
                    $term = Resolve-MgTermPath -TermSet $TermSet -Path $Matches[1]
                    if (-not $term) { throw "Unknown term '$($Matches[1])' in {$t}." }
                    return "$($term.Id)"
                }
                default { throw "Unknown token {$t}." }
            }
        })
}

function Split-MgKql([string]$Query) {
    # Tokens: parentheses, words (a quoted part can be inside a word: prop:"two words"), and unclosed-quote errors.
    # NEAR(n=4), ONEAR(4) and XRANK(cb=100) parameters aren't property restrictions: reduce them to the operator.
    $Query = [regex]::Replace($Query, '\b(NEAR|ONEAR|XRANK)\([^)]*\)', '$1')
    $tokens = [System.Collections.Generic.List[object]]::new()
    $i = 0; $n = $Query.Length
    while ($i -lt $n) {
        $ch = $Query[$i]
        if ([char]::IsWhiteSpace($ch)) { $i++; continue }
        if ($ch -eq '(' -or $ch -eq ')') { $tokens.Add([pscustomobject]@{ Text = "$ch"; Kind = 'Paren' }); $i++; continue }
        $start = $i; $open = $false
        while ($i -lt $n) {
            $ch = $Query[$i]
            if ($ch -eq '"') { $open = -not $open; $i++; continue }
            if (-not $open -and ([char]::IsWhiteSpace($ch) -or $ch -eq ')' -or ($ch -eq '(' -and $i -gt $start -and $Query[$i - 1] -ne ':'))) { break }
            if (-not $open -and $ch -eq '(' -and $i -gt $start) {
                # prop:(a b) grouping: keep the group inside the token
                $depth = 0
                while ($i -lt $n) { if ($Query[$i] -eq '(') { $depth++ } elseif ($Query[$i] -eq ')') { $depth--; if ($depth -eq 0) { $i++; break } }; $i++ }
                continue
            }
            $i++
        }
        $tokens.Add([pscustomobject]@{ Text = $Query.Substring($start, $i - $start); Kind = if ($open) { 'Unclosed' } else { 'Word' } })
    }
    $tokens
}

function Test-MgKql {
    <#
    .SYNOPSIS  Lints a KQL query (KQ001-KQ010) against the KQL syntax reference and the plan's property types.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Query, $Plan, [string]$Target = 'query', [switch]$FrontEnd)
    $props = Get-MgQueryProperties -Plan $Plan
    if ($Query.Length -gt $script:KqlMaxProgrammatic) {
        New-MgFinding 'KQ008' 'Error' $Target "$($Query.Length) characters: queries from code are limited to 4,096 by default."
    }
    elseif ($Query.Length -gt $script:KqlMaxFrontEnd) {
        New-MgFinding 'KQ008' $(if ($FrontEnd) { 'Error' } else { 'Warning' }) $Target "$($Query.Length) characters: the search box allows 2,048."
    }
    $tokens = @(Split-MgKql $Query)
    $depth = 0
    foreach ($t in $tokens) {
        if ($t.Kind -eq 'Unclosed') { New-MgFinding 'KQ009' 'Error' $Target "Unclosed quotation mark in '$($t.Text)'." }
        if ($t.Text -eq '(') { $depth++ } elseif ($t.Text -eq ')') { $depth-- }
        if ($depth -lt 0) { New-MgFinding 'KQ009' 'Error' $Target "')' without '('."; $depth = 0 }
    }
    if ($depth -gt 0) { New-MgFinding 'KQ009' 'Error' $Target "$depth '(' without ')'." }
    $words = @($tokens | Where-Object Kind -ne 'Paren')
    $operators = @('AND', 'OR', 'NOT', 'NEAR', 'ONEAR', 'WORDS', 'XRANK')
    if (-not @($words | Where-Object { $_.Text -notin $operators -and $_.Text -notmatch '^(NEAR|ONEAR|XRANK)\(' }).Count) {
        New-MgFinding 'KQ001' 'Error' $Target 'Empty, or only operators: not a valid query.'
        return
    }
    for ($k = 0; $k -lt $words.Count; $k++) {
        $w = $words[$k].Text
        if ($w -cin @('and', 'or', 'not', 'And', 'Or', 'Not')) {
            New-MgFinding 'KQ002' 'Warning' $Target "'$w' is searched as a word: operators are case-sensitive, write $($w.ToUpperInvariant())."
            continue
        }
        if ($w -match '^(:|=|<>|<=|>=|<|>)' -and $k -gt 0) {
            New-MgFinding 'KQ003' 'Error' $Target "White space before '$($Matches[1])' after '$($words[$k-1].Text)': the restriction becomes free text."
            continue
        }
        if ($w -match '^(?<p>[A-Za-z_][A-Za-z0-9_]*)(?<op>:|=|<>|<=|>=|<|>)(?<v>.*)$') {
            $p = $Matches['p']; $op = $Matches['op']; $v = $Matches['v']
            if ($v -eq '') {
                New-MgFinding 'KQ003' 'Error' $Target "White space after '$p$op': the restriction becomes free text."
                continue
            }
            if ($w.Length -gt $script:KqlMaxRestriction) { New-MgFinding 'KQ008' 'Error' $Target "Property restriction on $p is longer than 2,048 characters." }
            $type = $props[$p.ToLowerInvariant()]
            if (-not $type) {
                New-MgFinding 'KQ004' 'Warning' $Target "'$p' isn't a known managed property or alias: it must be a queryable managed property."
                continue
            }
            $isRange = $op -in @('<', '>', '<=', '>=') -or ($op -in @(':', '=') -and $v -match '^[^"]*\.\.')
            if ($isRange -and $type -notin $script:RangeTypes) {
                New-MgFinding 'KQ005' 'Error' $Target "'$p' is ${type}: '$op' and '..' only work on DateTime, Integer, Decimal and Double properties."
            }
            if ($type -eq 'DateTime') {
                foreach ($d in @($v.Trim('"') -split '\.\.')) {
                    if ($d -notmatch '^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d{1,7})?Z?)?$' -and $d.ToLowerInvariant() -notin $script:DateKeywords) {
                        New-MgFinding 'KQ007' 'Error' $Target "'$d' isn't a KQL date: use YYYY-MM-DD (UTC) or a keyword like today, ""this month""."
                    }
                }
            }
            if ($op -eq '=' -and $v -match '\*') { New-MgFinding 'KQ010' 'Warning' $Target "'=' with '*' on $p isn't recommended: use ':' for prefix matching." }
            if ($v.TrimStart('"').StartsWith('*') -and $v.Trim('"') -ne '*') { New-MgFinding 'KQ006' 'Warning' $Target "'$v': KQL doesn't support a wildcard at the start of a term." }
            continue
        }
        if ($w.TrimStart('"').StartsWith('*')) { New-MgFinding 'KQ006' 'Warning' $Target "'$w': KQL doesn't support a wildcard at the start of a term." }
    }
}

# ---- Live checks ---------------------------------------------------------------------------------------------------

function Test-MgSearchMapping {
    <#
    .SYNOPSIS  Compares the plan with the site collection's custom mappings (Get-PnPSearchConfiguration -OutputFormat
               ManagedPropertyMappings: objects with Name, Aliases, Mappings). SM001-SM003.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Mappings)
    $columns = @{}; foreach ($c in @($Plan.columns)) { $columns[$c.internalName] = $c }
    foreach ($m in @($Plan.mappings)) {
        $target = "mapping '$($m.managedProperty)'"
        $live = @($Mappings | Where-Object Name -eq $m.managedProperty) | Select-Object -First 1
        $expected = if (Get-MgProp $m 'crawledProperty') { @($m.crawledProperty) } else { Get-MgCrawledCandidates $columns[$m.column] }
        if (-not $live -or -not @($live.Mappings | Where-Object { $_ -in $expected }).Count) {
            New-MgFinding 'SM001' 'Error' $target "Not mapped to $($expected -join ' or ') on this site collection: map it in Site settings > Search Schema."
            continue
        }
        if ((Get-MgProp $m 'alias') -and $m.alias -notin @($live.Aliases)) {
            New-MgFinding 'SM002' 'Error' $target "Alias '$($m.alias)' is missing: queries using it won't match."
        }
        $extra = @($live.Mappings | Where-Object { $_ -notin $expected })
        if ($extra.Count) { New-MgFinding 'SM003' 'Warning' $target "Also mapped to $($extra -join ', '): values from other columns mix in." }
    }
}

function Test-MgSearchResult {
    <#
    .SYNOPSIS  Checks one search test's result against its expectations (count, minimum, file names, refiner values).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Test, [Parameter(Mandatory)]$Result)
    $exp = Get-MgProp $Test 'expect'
    $problems = [System.Collections.Generic.List[string]]::new()
    $names = @($Result.Rows | ForEach-Object { $n = Get-MgProp $_ 'Filename'; if (-not $n) { $n = Split-Path -Leaf ([uri]::UnescapeDataString("$(Get-MgProp $_ 'Path')")) }; $n })
    if ($null -ne (Get-MgProp $exp 'count') -and $Result.Rows.Count -ne $exp.count) { $problems.Add("expected $($exp.count) result(s), got $($Result.Rows.Count)") }
    if ($null -ne (Get-MgProp $exp 'min') -and $Result.Rows.Count -lt $exp.min) { $problems.Add("expected at least $($exp.min) result(s), got $($Result.Rows.Count)") }
    foreach ($like in @(Get-MgProp $exp 'files' @())) {
        if (-not @($names | Where-Object { $_ -like $like }).Count) { $problems.Add("no result like '$like'") }
    }
    foreach ($r in @((Get-MgProp $exp 'refiners' ([pscustomobject]@{})).PSObject.Properties)) {
        $have = @($Result.Refiners | Where-Object RefinerName -eq $r.Name | ForEach-Object RefinementName)
        foreach ($v in @($r.Value)) { if ($v -notin $have) { $problems.Add("refiner $($r.Name) has no '$v' (has: $($have -join ', '))") } }
    }
    [pscustomobject]@{ Name = $Test.name; Passed = ($problems.Count -eq 0); Count = $Result.Rows.Count; Files = $names; Problems = @($problems) }
}

# ---- Tenant --------------------------------------------------------------------------------------------------------

function Invoke-MgTaxonomyProvisioning {
    <#
    .SYNOPSIS  Creates the term group, term set and terms with their fixed IDs (idempotent, -WhatIf). Term store admin.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$TermSet, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $lcid = [int](Get-MgProp $TermSet.termSet 'lcid' 1033)
    $gid = [guid]$TermSet.group.id; $sid = [guid]$TermSet.termSet.id
    function Find([scriptblock]$Get) { try { & $Get } catch { $null } }
    if (-not (Find { Get-PnPTermGroup -Identity $gid -ErrorAction Stop @c })) {
        if ($PSCmdlet.ShouldProcess($TermSet.group.name, 'New term group')) { $null = New-PnPTermGroup -Name $TermSet.group.name -Id $gid @c }
        [pscustomobject]@{ Action = 'AddTermGroup'; Target = $TermSet.group.name; Detail = "$gid" }
    }
    if (-not (Find { Get-PnPTermSet -Identity $sid -TermGroup $gid -ErrorAction Stop @c })) {
        if ($PSCmdlet.ShouldProcess($TermSet.termSet.name, 'New term set')) { $null = New-PnPTermSet -Name $TermSet.termSet.name -Id $sid -TermGroup $gid -Lcid $lcid @c }
        [pscustomobject]@{ Action = 'AddTermSet'; Target = $TermSet.termSet.name; Detail = "$sid" }
    }
    foreach ($t in Get-MgTermList $TermSet.terms) {
        $tid = [guid]$t.Id
        if (Find { Get-PnPTerm -Identity $tid -TermSet $sid -TermGroup $gid -Recursive -ErrorAction Stop @c }) { continue }
        if ($PSCmdlet.ShouldProcess($t.Path, 'New term')) {
            if ($t.ParentId) { $null = Add-PnPTermToTerm -ParentTermId ([guid]$t.ParentId) -Name $t.Name -Id $tid -Lcid $lcid @c }
            else { $null = New-PnPTerm -Name $t.Name -Id $tid -TermSet $sid -TermGroup $gid -Lcid $lcid @c }
        }
        [pscustomobject]@{ Action = 'AddTerm'; Target = $t.Path; Detail = "$tid" }
    }
}

function Invoke-MgCategoryColumn {
    <#
    .SYNOPSIS  Adds the managed metadata site column and pushes it to the content type and its children (-WhatIf).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Plan, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $col = $Plan.categoryColumn
    $field = Get-PnPField -Identity $col.internalName -ErrorAction SilentlyContinue @c
    if (-not $field) {
        if ($PSCmdlet.ShouldProcess($col.internalName, 'Add taxonomy site column')) {
            $null = Add-PnPTaxonomyField -DisplayName $col.displayName -InternalName $col.internalName -TermSetPath $col.termSetPath -Group $col.group -Id ([guid]$col.id) @c
        }
        [pscustomobject]@{ Action = 'AddColumn'; Target = $col.internalName; Detail = $col.termSetPath }
    }
    $inList = Get-PnPField -List $Plan.library -Identity $col.internalName -ErrorAction SilentlyContinue @c
    if (-not $inList) {
        if ($PSCmdlet.ShouldProcess($col.contentType, "Add $($col.internalName) to content type")) {
            Add-PnPFieldToContentType -Field $col.internalName -ContentType $col.contentType -UpdateChildren $true @c
        }
        [pscustomobject]@{ Action = 'AddFieldLink'; Target = $col.contentType; Detail = "$($col.internalName) (children updated)" }
    }
}

function Invoke-MgCategoryTagging {
    <#
    .SYNOPSIS  Sets Category on every file whose Supplier has a category in the plan (idempotent, -WhatIf).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param([Parameter(Mandatory)]$Plan, [Parameter(Mandatory)]$TermSet, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    $field = $Plan.categoryColumn.internalName
    $map = @{}
    foreach ($p in @($Plan.supplierCategories.PSObject.Properties)) { $map[$p.Name] = Resolve-MgTermPath -TermSet $TermSet -Path $p.Value }
    foreach ($it in @(Get-PnPListItem -List $Plan.library -PageSize 500 -Fields 'FileLeafRef', 'FSObjType', 'Supplier', $field @c)) {
        if ("$($it['FSObjType'])" -ne '0') { continue }
        $supplier = "$($it['Supplier'])"
        $term = $map[$supplier]
        if (-not $term) {
            [pscustomobject]@{ Action = 'Skip'; Target = $it['FileLeafRef']; Detail = $(if ($supplier) { "no category for '$supplier'" } else { 'no supplier' }) }
            continue
        }
        $current = $it[$field]
        if ($current -and "$(Get-MgProp $current 'TermGuid')" -eq "$($term.Id)") { continue }
        if ($PSCmdlet.ShouldProcess($it['FileLeafRef'], "Category = $($term.Path)")) {
            $null = Set-PnPListItem -List $Plan.library -Identity $it.Id -Values @{ $field = "$($term.Id)" } -UpdateType SystemUpdate @c
        }
        [pscustomobject]@{ Action = 'Tag'; Target = $it['FileLeafRef']; Detail = $term.Path }
    }
}

function Get-MgSiteSearchMapping {
    <#
    .SYNOPSIS  The site collection's custom managed properties with their aliases and crawled property mappings.
    #>
    [CmdletBinding()]
    param($Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    @(Get-PnPSearchConfiguration -Scope Site -OutputFormat ManagedPropertyMappings @c)
}

function Invoke-MgSearchTest {
    <#
    .SYNOPSIS  Runs each search test with Submit-PnPSearchQuery and checks the results. Lint-only tests aren't run.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)]$Tests, $Plan, $TermSet, [Parameter(Mandatory)][string]$SiteUrl, [datetime]$Today = (Get-Date).Date, $Connection)
    $c = @{}; if ($Connection) { $c.Connection = $Connection }
    foreach ($t in @($Tests.tests)) {
        if (Get-MgProp $t 'lintOnly' $false) { continue }
        $kql = ConvertTo-MgKql -Template $t.query -Plan $Plan -TermSet $TermSet -SiteUrl $SiteUrl -Today $Today
        $q = @{ Query = $kql; MaxResults = 100; SelectProperties = @('Title', 'Filename', 'Path') + @(Get-MgProp $t 'select' @()) }
        if (Get-MgProp $t 'refiners') { $q.Refiners = $t.refiners }
        $tables = @(Submit-PnPSearchQuery @q @c)
        $rows = @(($tables | Where-Object TableType -eq 'RelevantResults' | Select-Object -First 1).ResultRows | Where-Object { $_ })
        $refiners = @(($tables | Where-Object TableType -eq 'RefinementResults' | Select-Object -First 1) | ForEach-Object { $_.ResultRows } | Where-Object { $_ } |
                ForEach-Object { [pscustomobject]@{ RefinerName = $_['RefinerName']; RefinementName = $_['RefinementName']; RefinementCount = $_['RefinementCount'] } })
        $r = Test-MgSearchResult -Test $t -Result ([pscustomobject]@{ Rows = $rows; Refiners = $refiners })
        $r | Add-Member -NotePropertyName Query -NotePropertyValue $kql -PassThru
    }
}

Export-ModuleMember -Function Import-MgJson, Get-MgAutoPropertyName, Get-MgManagedPropertyInfo, Test-MgTermSet, Resolve-MgTermPath,
    Test-MgSearchPlan, Get-MgQueryProperties, ConvertTo-MgKql, Test-MgKql, Test-MgSearchMapping, Test-MgSearchResult,
    Invoke-MgTaxonomyProvisioning, Invoke-MgCategoryColumn, Invoke-MgCategoryTagging, Get-MgSiteSearchMapping, Invoke-MgSearchTest
