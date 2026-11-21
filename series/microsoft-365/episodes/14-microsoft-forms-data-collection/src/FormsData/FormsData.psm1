#Requires -Version 7.2
<#
.SYNOPSIS
    Microsoft Forms data collection, as code (DEVLADLOG Microsoft 365 #14).

    Microsoft Forms has no public API to create a form or read its responses. What a form CAN do (Learn, Forms connector):
    trigger a Power Automate flow with "When a new response is submitted" and offer "Get response details". So the data
    collection design here is: Form (made by hand) -> flow (made by hand) -> SharePoint list (provisioned by this module from
    one JSON spec) -> analysis (this module reads the list through Microsoft Graph).

      * Spec validation, then the list and its columns as a Graph body; create the list or ADD missing columns (never change or
        delete a column that holds data), honoring -WhatIf.
      * A mapping table question -> column -> what the flow's "Create item" action needs.
      * Read the responses (paged) and find data-quality problems; summarise the answers.
    Graph v1.0 used, with the delegated scope each call needs (Learn):
      GET  /sites/{hostname}:/{path}                        Sites.Read.All
      GET  /sites/{id}/lists, /lists/{id}/columns, /items   Sites.Read.All
      POST /sites/{id}/lists, /lists/{id}/columns           Sites.Manage.All
#>
Set-StrictMode -Version Latest

$script:Graph = '/v1.0'
$script:SeverityOrder = @{ High = 3; Medium = 2; Low = 1; Info = 0 }
$script:QuestionTypes = 'text', 'longText', 'choice', 'multiChoice', 'rating', 'number', 'yesNo', 'date'
# Columns that exist in a genericList or are added by SharePoint; our rule: a question must not reuse them.
$script:Reserved = 'Title', 'ID', 'Id', 'Author', 'Editor', 'Created', 'Modified', 'ResponseId', 'Responder', 'Submitted', 'Attachments', 'ContentType'

function Get-FDProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($p -and $null -ne $p.Value) { $p.Value } else { $Default }
}

function Get-FDSpec {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path $Path)) { throw "Spec file not found: $Path" }
    $s = Get-Content $Path -Raw | ConvertFrom-Json
    $url = [string](Get-FDProp (Get-FDProp $s 'site') 'url' '')
    $u = $null
    if (-not [uri]::TryCreate($url, 'Absolute', [ref]$u) -or $u.Scheme -ne 'https' -or $u.AbsolutePath.Length -lt 2) { throw "Spec: site.url must be an https URL of a SharePoint site, like https://contoso.sharepoint.com/sites/name. Got '$url'." }
    if (-not [string](Get-FDProp (Get-FDProp $s 'list') 'displayName' '')) { throw 'Spec: list.displayName is required.' }
    $qs = @(Get-FDProp $s 'questions' @())
    if ($qs.Count -eq 0) { throw 'Spec: at least one question is required.' }
    $seen = @{}
    foreach ($q in $qs) {
        $col = [string](Get-FDProp $q 'column' '')
        if ($col -notmatch '^[A-Za-z][A-Za-z0-9_]{0,31}$') { throw "Spec: column '$col' must start with a letter and use only letters, digits and underscores (32 characters at most)." }
        if ($col -in $script:Reserved) { throw "Spec: column '$col' collides with a built-in or response column ($($script:Reserved -join ', '))." }
        if ($seen.ContainsKey($col.ToLowerInvariant())) { throw "Spec: column '$col' is used twice." }
        $seen[$col.ToLowerInvariant()] = $true
        if (-not [string](Get-FDProp $q 'title' '')) { throw "Spec: question for column '$col' needs a title (the question text in the form)." }
        $t = [string](Get-FDProp $q 'type' '')
        if ($t -notin $script:QuestionTypes) { throw "Spec: question type '$t' of column '$col' is not one of: $($script:QuestionTypes -join ', ')." }
        if ($t -in 'choice', 'multiChoice') {
            $ch = @(Get-FDProp $q 'choices' @())
            if ($ch.Count -lt 2) { throw "Spec: column '$col' needs at least two choices." }
            if (@($ch | Select-Object -Unique).Count -ne $ch.Count) { throw "Spec: column '$col' has duplicate choices." }
        }
        if ($t -in 'rating', 'number') {
            $mn = Get-FDProp $q 'min'; $mx = Get-FDProp $q 'max'
            if ($t -eq 'rating' -and ($null -eq $mn -or $null -eq $mx)) { throw "Spec: rating column '$col' needs min and max." }
            if ($null -ne $mn -and $null -ne $mx -and $mn -ge $mx) { throw "Spec: column '$col' has min >= max." }
        }
        $ml = Get-FDProp $q 'maxLength'
        if ($null -ne $ml -and (($ml -isnot [int] -and $ml -isnot [long]) -or $ml -lt 1 -or ($ml -gt 255 -and $t -eq 'text'))) { throw "Spec: maxLength of column '$col' must be a whole number from 1 (single-line text: up to 255)." }
    }
    $a = Get-FDProp $s 'audit'
    foreach ($n in 'duplicateWindowMinutes', 'lowRating') {
        $v = Get-FDProp $a $n
        if ($null -ne $v -and (($v -isnot [int] -and $v -isnot [long]) -or $v -lt 1)) { throw "Spec: audit.$n must be a whole number of 1 or more." }
    }
    $s
}

# ---------------------------------------------------------------- Graph bodies

function ConvertTo-FDColumn {
    <# One question -> one Graph columnDefinition. Facet names and values are the ones on Learn (text, choice, number, dateTime, boolean). #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Question)
    $c = [ordered]@{ name = [string]$Question.column; displayName = [string]$Question.column; description = [string]$Question.title }
    if (Get-FDProp $Question 'required' $false) { $c.required = $true }
    switch ([string]$Question.type) {
        'text' { $c.text = [ordered]@{ maxLength = [int](Get-FDProp $Question 'maxLength' 255) } }
        'longText' { $c.text = [ordered]@{ allowMultipleLines = $true; textType = 'plain'; maxLength = [int](Get-FDProp $Question 'maxLength' 1000) } }
        'choice' { $c.choice = [ordered]@{ allowTextEntry = $false; displayAs = 'dropDownMenu'; choices = @($Question.choices) } }
        'multiChoice' { $c.choice = [ordered]@{ allowTextEntry = $false; displayAs = 'checkBoxes'; choices = @($Question.choices) } }
        'rating' { $c.number = [ordered]@{ decimalPlaces = 'none'; minimum = [double]$Question.min; maximum = [double]$Question.max } }
        'number' {
            $n = [ordered]@{ decimalPlaces = [string](Get-FDProp $Question 'decimalPlaces' 'automatic') }
            if ($null -ne (Get-FDProp $Question 'min')) { $n.minimum = [double]$Question.min }
            if ($null -ne (Get-FDProp $Question 'max')) { $n.maximum = [double]$Question.max }
            $c.number = $n
        }
        'yesNo' { $c.boolean = [ordered]@{} }
        'date' { $c.dateTime = [ordered]@{ format = 'dateOnly'; displayAs = 'default' } }
    }
    $c
}

function Get-FDMetaColumn {
    <# The columns the flow fills besides the answers. ResponseId is unique, so a flow that runs twice for one response cannot write it twice. #>
    @(
        [ordered]@{ name = 'ResponseId'; displayName = 'ResponseId'; description = "Forms response id (the trigger's Response Id)"; required = $true; indexed = $true; enforceUniqueValues = $true; number = [ordered]@{ decimalPlaces = 'none' } }
        [ordered]@{ name = 'Responder'; displayName = 'Responder'; description = "Responders' Email from Get response details (empty when the response is anonymous)"; text = [ordered]@{ maxLength = 255 } }
        [ordered]@{ name = 'Submitted'; displayName = 'Submitted'; description = 'Submission time from Get response details'; dateTime = [ordered]@{ format = 'dateTime'; displayAs = 'default' } }
    )
}

function ConvertTo-FDListBody {
    [CmdletBinding()] param([Parameter(Mandatory)]$Spec)
    $cols = @(Get-FDMetaColumn) + @($Spec.questions | ForEach-Object { ConvertTo-FDColumn -Question $_ })
    [ordered]@{
        displayName = [string]$Spec.list.displayName
        description = [string](Get-FDProp $Spec.list 'description' '')
        columns     = $cols
        list        = [ordered]@{ template = 'genericList' }
    }
}

function Get-FDFlowMap {
    <# What the Power Automate flow must write, per column: the table you follow when building "Create item". #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Spec)
    $rows = @(
        [pscustomobject]@{ Column = 'Title'; Type = 'text'; From = 'a label, for example "Response " + Response Id'; Note = 'genericList has a Title column' }
        [pscustomobject]@{ Column = 'ResponseId'; Type = 'number'; From = 'trigger: Response Id'; Note = 'unique: a second write is rejected' }
        [pscustomobject]@{ Column = 'Responder'; Type = 'text'; From = "Get response details: Responders' Email"; Note = 'empty if anonymous' }
        [pscustomobject]@{ Column = 'Submitted'; Type = 'dateTime'; From = 'Get response details: the submission time (check the dynamic content name in the designer)'; Note = '' }
    )
    foreach ($q in $Spec.questions) {
        $kind = switch ($q.type) { 'multiChoice' { 'multi-select: send the selected values' } 'yesNo' { 'Forms Yes/No answer as true/false' } default { '' } }
        $rows += [pscustomobject]@{ Column = $q.column; Type = $q.type; From = "Get response details: '$($q.title)'"; Note = $kind }
    }
    $rows
}

# ---------------------------------------------------------------- Graph calls

function Invoke-FDGraph {
    [CmdletBinding()] param([string]$Method = 'GET', [Parameter(Mandatory)][string]$Uri, $Body)
    $p = @{ Method = $Method; Uri = $Uri; ErrorAction = 'Stop' }
    if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Depth 10); $p.ContentType = 'application/json' }
    Invoke-MgGraphRequest @p
}

function Get-FDPaged {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Uri)
    while ($Uri) {
        $r = Invoke-FDGraph -Uri $Uri
        foreach ($v in @(Get-FDProp $r 'value' @())) { $v }
        $Uri = Get-FDProp $r '@odata.nextLink'
    }
}

function Get-FDSiteId {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Url)
    $u = [uri]$Url
    $r = Invoke-FDGraph -Uri ("$script:Graph/sites/{0}:{1}" -f $u.Host, $u.AbsolutePath.TrimEnd('/'))
    [string](Get-FDProp $r 'id')
}

function Get-FDList {
    <# The list by display name (all lists are paged and filtered here: $filter is not documented for lists). #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$SiteId, [Parameter(Mandatory)][string]$DisplayName)
    @(Get-FDPaged -Uri "$script:Graph/sites/$SiteId/lists?`$select=id,displayName,list" | Where-Object { $_.displayName -eq $DisplayName })
}

function Compare-FDColumn {
    <# Wanted columns vs the columns in the tenant. Returns Missing (names to add) and Drift (a column that exists but differs: reported, never changed). #>
    [CmdletBinding()] param([Parameter(Mandatory)][object[]]$Wanted, [Parameter(Mandatory)][object[]]$Existing)
    $have = @{}; foreach ($e in $Existing) { $have[([string]$e.name).ToLowerInvariant()] = $e }
    $missing = [System.Collections.Generic.List[object]]::new(); $drift = [System.Collections.Generic.List[string]]::new()
    foreach ($w in $Wanted) {
        $k = ([string]$w['name']).ToLowerInvariant()
        if (-not $have.ContainsKey($k)) { $missing.Add($w); continue }
        $e = $have[$k]
        foreach ($facet in 'text', 'choice', 'number', 'dateTime', 'boolean') {
            if ($w.Contains($facet) -and -not (Get-FDProp $e $facet)) { $drift.Add("$($w['name']): wanted a $facet column") }
        }
        if ($w.Contains('choice')) {
            $ec = @(Get-FDProp (Get-FDProp $e 'choice') 'choices' @())
            if ($ec.Count -and (@($w['choice']['choices'] | Sort-Object) -join '|') -ne (@($ec | Sort-Object) -join '|')) { $drift.Add("$($w['name']): choices differ from the spec") }
        }
        if ($w.Contains('number')) {
            $en = Get-FDProp $e 'number'
            foreach ($b in 'minimum', 'maximum') { if ($w['number'].Contains($b) -and "$(Get-FDProp $en $b)" -ne "$($w['number'][$b])") { $drift.Add("$($w['name']): $b is '$(Get-FDProp $en $b)', the spec says '$($w['number'][$b])'") } }
        }
    }
    [pscustomobject]@{ Missing = @($missing); Drift = @($drift) }
}

function Set-FDList {
    <# Creates the list, or adds the columns that are missing. Existing columns are never changed or deleted: their data would be at risk. #>
    [CmdletBinding(SupportsShouldProcess)] param([Parameter(Mandatory)]$Spec)
    $body = ConvertTo-FDListBody -Spec $Spec
    $siteId = Get-FDSiteId -Url $Spec.site.url
    if (-not $siteId) { throw "Site not found: $($Spec.site.url)" }
    $found = @(Get-FDList -SiteId $siteId -DisplayName $body.displayName)
    if ($found.Count -gt 1) { throw "More than one list is called '$($body.displayName)'." }
    $row = [ordered]@{ List = $body.displayName; Action = ''; Added = ''; Drift = ''; Id = '' }
    if ($found.Count -eq 0) {
        $row.Action = 'Create'
        if ($PSCmdlet.ShouldProcess($body.displayName, 'create list with ' + $body.columns.Count + ' columns')) {
            $new = Invoke-FDGraph -Method POST -Uri "$script:Graph/sites/$siteId/lists" -Body $body
            $row.Action = 'Created'; $row.Id = [string](Get-FDProp $new 'id'); $row.Added = ($body.columns | ForEach-Object { $_['name'] }) -join ', '
        } else { $row.Action = 'WhatIf-Create' }
        return [pscustomobject]$row
    }
    $listId = [string]$found[0].id; $row.Id = $listId
    $existing = @(Get-FDPaged -Uri "$script:Graph/sites/$siteId/lists/$listId/columns")
    $cmp = Compare-FDColumn -Wanted $body.columns -Existing $existing
    $row.Drift = $cmp.Drift -join '; '
    if ($cmp.Missing.Count -eq 0) { $row.Action = 'Unchanged'; return [pscustomobject]$row }
    $row.Action = 'AddColumns'; $names = @()
    foreach ($m in $cmp.Missing) {
        if ($PSCmdlet.ShouldProcess("$($body.displayName).$($m['name'])", 'add column')) {
            $null = Invoke-FDGraph -Method POST -Uri "$script:Graph/sites/$siteId/lists/$listId/columns" -Body $m
            $names += $m['name']
        } else { $names += "WhatIf:$($m['name'])" }
    }
    $row.Added = $names -join ', '
    if ($names.Count -and -not ($names | Where-Object { $_ -notlike 'WhatIf:*' })) { $row.Action = 'WhatIf-AddColumns' } else { $row.Action = 'ColumnsAdded' }
    [pscustomobject]$row
}

function Get-FDResponse {
    <# The list items with their column values: GET .../items?expand=fields. #>
    [CmdletBinding()] param([string]$Path, [string]$SiteUrl, [string]$ListName)
    if ($Path) { return @(Get-Content $Path -Raw | ConvertFrom-Json).value }
    $siteId = Get-FDSiteId -Url $SiteUrl
    $l = @(Get-FDList -SiteId $siteId -DisplayName $ListName)
    if ($l.Count -ne 1) { throw "Expected one list called '$ListName', found $($l.Count)." }
    @(Get-FDPaged -Uri "$script:Graph/sites/$siteId/lists/$($l[0].id)/items?expand=fields")
}

# ---------------------------------------------------------------- analysis (pure)

function Test-FDEmpty($v) { $null -eq $v -or ($v -is [string] -and [string]::IsNullOrWhiteSpace($v)) -or ($v -is [array] -and $v.Count -eq 0) }

function Get-FDResponseFinding {
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Items, [Parameter(Mandatory)]$Spec)
    $audit = Get-FDProp $Spec 'audit'
    $window = [int](Get-FDProp $audit 'duplicateWindowMinutes' 10); $low = [int](Get-FDProp $audit 'lowRating' 2)
    $out = [System.Collections.Generic.List[object]]::new()
    function Add-F($Sev, $Type, $Id, $Detail) { $out.Add([pscustomobject]@{ Severity = $Sev; Type = $Type; ResponseId = $Id; Detail = $Detail }) }
    $rows = foreach ($i in $Items) { [pscustomobject]@{ Fields = Get-FDProp $i 'fields' $i; Item = $i } }
    foreach ($r in $rows) {
        $f = $r.Fields; $rid = Get-FDProp $f 'ResponseId'
        foreach ($q in $Spec.questions) {
            $v = Get-FDProp $f $q.column
            if ((Get-FDProp $q 'required' $false) -and (Test-FDEmpty $v)) { Add-F 'Medium' 'MissingRequired' $rid "'$($q.column)' is required in the spec and empty."; continue }
            if (Test-FDEmpty $v) { continue }
            if ($q.type -in 'choice', 'multiChoice') {
                foreach ($x in @($v)) { if ($x -notin @($q.choices)) { Add-F 'Medium' 'InvalidChoice' $rid "'$($q.column)' holds '$x', which is not one of the choices." } }
            }
            if ($q.type -in 'rating', 'number') {
                $n = 0.0
                if (-not [double]::TryParse("$v", [cultureinfo]::InvariantCulture, [ref]$n)) { Add-F 'Medium' 'NotANumber' $rid "'$($q.column)' holds '$v'." }
                else {
                    $mn = Get-FDProp $q 'min'; $mx = Get-FDProp $q 'max'
                    if (($null -ne $mn -and $n -lt $mn) -or ($null -ne $mx -and $n -gt $mx)) { Add-F 'Medium' 'OutOfRange' $rid "'$($q.column)' is $n, outside $mn..$mx." }
                }
            }
        }
        if (Test-FDEmpty (Get-FDProp $f 'Responder')) { Add-F 'Info' 'AnonymousResponder' $rid 'No responder recorded: an anonymous response, or the form or tenant does not record names.' }
        foreach ($q in @($Spec.questions | Where-Object { $_.type -eq 'rating' })) {
            $rv = Get-FDProp $f $q.column; $cq = $Spec.questions | Where-Object { $_.type -eq 'longText' } | Select-Object -First 1
            if (-not (Test-FDEmpty $rv) -and [double]$rv -le $low -and $cq -and (Test-FDEmpty (Get-FDProp $f $cq.column))) { Add-F 'Low' 'LowRatingNoComment' $rid "Rating $rv with no '$($cq.column)': nothing to act on." }
        }
    }
    # The same ResponseId twice: the flow ran twice for one response (the unique column should prevent it).
    foreach ($g in ($rows | Where-Object { $null -ne (Get-FDProp $_.Fields 'ResponseId') } | Group-Object { "$(Get-FDProp $_.Fields 'ResponseId')" } | Where-Object Count -gt 1)) {
        Add-F 'High' 'DuplicateResponseId' $g.Name "$($g.Count) rows for one Forms response (a flow retry or a second flow)."
    }
    # Ids missing between 1 and the highest: deleted in Forms, or the flow never ran for them. Learn does not promise that ids are consecutive.
    $ids = @($rows | ForEach-Object { Get-FDProp $_.Fields 'ResponseId' } | Where-Object { $null -ne $_ } | ForEach-Object { [int]$_ } | Sort-Object -Unique)
    if ($ids.Count) {
        $gaps = @(1..$ids[-1] | Where-Object { $_ -notin $ids })
        if ($gaps.Count) { Add-F 'Info' 'ResponseIdGap' ($gaps -join ',') "No row for response id(s) $($gaps -join ', '): deleted in Forms, or the flow missed them. Compare with the Forms Responses tab." }
    }
    # Same person, same answers, close together: a double submit.
    $withTime = @($rows | Where-Object { (Get-FDProp $_.Fields 'Responder') -and (Get-FDProp $_.Fields 'Submitted') })
    foreach ($g in ($withTime | Group-Object { (Get-FDProp $_.Fields 'Responder') })) {
        $sorted = @($g.Group | Sort-Object { [datetimeoffset](Get-FDProp $_.Fields 'Submitted') })
        for ($k = 1; $k -lt $sorted.Count; $k++) {
            $a = $sorted[$k - 1].Fields; $b = $sorted[$k].Fields
            $same = -not @($Spec.questions | Where-Object { (@(Get-FDProp $a $_.column) -join ';') -ne (@(Get-FDProp $b $_.column) -join ';') }).Count
            $gap = ([datetimeoffset](Get-FDProp $b 'Submitted') - [datetimeoffset](Get-FDProp $a 'Submitted')).TotalMinutes
            if ($same -and $gap -le $window -and (Get-FDProp $a 'ResponseId') -ne (Get-FDProp $b 'ResponseId')) { Add-F 'Low' 'PossibleDoubleSubmit' (Get-FDProp $b 'ResponseId') "Same answers as response $(Get-FDProp $a 'ResponseId') from the same responder $([math]::Round($gap, 1)) min earlier." }
        }
    }
    @($out | Sort-Object { -$script:SeverityOrder[$_.Severity] }, Type)
}

function Get-FDSummary {
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Items, [Parameter(Mandatory)]$Spec)
    $fields = @($Items | ForEach-Object { Get-FDProp $_ 'fields' $_ })
    $res = [ordered]@{ Total = $fields.Count; Questions = [System.Collections.Generic.List[object]]::new(); PerDay = @() }
    foreach ($q in $Spec.questions) {
        $vals = @($fields | ForEach-Object { Get-FDProp $_ $q.column } | Where-Object { -not (Test-FDEmpty $_) })
        $answered = @($fields | Where-Object { -not (Test-FDEmpty (Get-FDProp $_ $q.column)) }).Count
        $e = [ordered]@{ Column = $q.column; Type = $q.type; Answered = $answered }
        switch ($q.type) {
            { $_ -in 'choice', 'multiChoice' } { $e.Counts = [ordered]@{}; foreach ($c in $q.choices) { $e.Counts[$c] = @($vals | ForEach-Object { $_ } | Where-Object { $_ -eq $c }).Count } }
            { $_ -in 'rating', 'number' } {
                $nums = @($vals | ForEach-Object { [double]$_ })
                if ($nums.Count) { $m = $nums | Measure-Object -Average -Minimum -Maximum; $e.Average = [math]::Round($m.Average, 2); $e.Min = $m.Minimum; $e.Max = $m.Maximum }
                if ($_ -eq 'rating') { $e.Counts = [ordered]@{}; for ($n = [int]$q.min; $n -le [int]$q.max; $n++) { $e.Counts["$n"] = @($nums | Where-Object { $_ -eq $n }).Count } }
            }
            'yesNo' { $e.Yes = @($vals | Where-Object { $_ -eq $true }).Count; $e.No = @($vals | Where-Object { $_ -eq $false }).Count }
        }
        $res.Questions.Add([pscustomobject]$e)
    }
    $res.PerDay = @($fields | Where-Object { Get-FDProp $_ 'Submitted' } | Group-Object { ([datetimeoffset](Get-FDProp $_ 'Submitted')).UtcDateTime.ToString('yyyy-MM-dd') } | Sort-Object Name | ForEach-Object { [pscustomobject]@{ Day = $_.Name; Responses = $_.Count } })
    [pscustomobject]$res
}

function ConvertTo-FDMarkdown {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Title, [Parameter(Mandatory)]$Summary, [object[]]$Findings = @(), [string]$Asof = '')
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine("# $Title"); $null = $sb.AppendLine()
    if ($Asof) { $null = $sb.AppendLine("_As of $Asof._"); $null = $sb.AppendLine() }
    $null = $sb.AppendLine("**$($Summary.Total) response(s).**"); $null = $sb.AppendLine()
    $null = $sb.AppendLine('| Question | Answered | Result |'); $null = $sb.AppendLine('|---|---|---|')
    foreach ($q in $Summary.Questions) {
        $r = if ($q.PSObject.Properties['Counts'] -and $q.Type -ne 'rating') { ($q.Counts.GetEnumerator() | ForEach-Object { "$($_.Key): $($_.Value)" }) -join ', ' }
        elseif ($q.PSObject.Properties['Average']) { "average $($q.Average) (min $($q.Min), max $($q.Max)); " + (($q.Counts.GetEnumerator() | ForEach-Object { "$($_.Key): $($_.Value)" }) -join ', ') }
        elseif ($q.PSObject.Properties['Yes']) { "yes $($q.Yes), no $($q.No)" } else { '' }
        $null = $sb.AppendLine("| $($q.Column) | $($q.Answered) | $r |")
    }
    $null = $sb.AppendLine()
    if ($Summary.PerDay.Count) { $null = $sb.AppendLine('Per day (UTC): ' + (($Summary.PerDay | ForEach-Object { "$($_.Day): $($_.Responses)" }) -join ', ')); $null = $sb.AppendLine() }
    $sorted = @($Findings | Sort-Object { -$script:SeverityOrder[$_.Severity] }, Type)
    $null = $sb.AppendLine("**$($sorted.Count) data-quality finding(s):** " + ((@('High', 'Medium', 'Low', 'Info') | ForEach-Object { "$(@($sorted | Where-Object Severity -eq $_).Count) $_" }) -join ' / '))
    $null = $sb.AppendLine()
    if ($sorted.Count) {
        $null = $sb.AppendLine('| Severity | Type | Response | Detail |'); $null = $sb.AppendLine('|---|---|---|---|')
        foreach ($f in $sorted) { $null = $sb.AppendLine("| $($f.Severity) | $($f.Type) | $($f.ResponseId) | $(([string]$f.Detail) -replace '\|', '/') |") }
    }
    $sb.ToString()
}

Export-ModuleMember -Function Get-FDSpec, ConvertTo-FDColumn, Get-FDMetaColumn, ConvertTo-FDListBody, Get-FDFlowMap, Get-FDSiteId, Get-FDList,
    Compare-FDColumn, Set-FDList, Get-FDResponse, Get-FDResponseFinding, Get-FDSummary, ConvertTo-FDMarkdown
