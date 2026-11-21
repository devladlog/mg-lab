BeforeAll {
    if (-not (Get-Command Invoke-MgGraphRequest -ErrorAction SilentlyContinue)) {
        Set-Item -Path function:global:Invoke-MgGraphRequest -Value ([scriptblock]::Create("[CmdletBinding()] param(`$Method, `$Uri, `$Body, `$ContentType, `$OutputType, `$Headers, `$OutputFilePath) throw 'stub: not connected'"))
    }
    Import-Module "$PSScriptRoot/../src/FormsData/FormsData.psd1" -Force
    $script:specPath = "$PSScriptRoot/../src/form.json"
    $script:spec = Get-FDSpec -Path $specPath
    $script:items = @((Get-Content "$PSScriptRoot/fixtures/items.json" -Raw | ConvertFrom-Json).value)

    function script:New-Spec([scriptblock]$Change) {
        $s = Get-Content $specPath -Raw | ConvertFrom-Json; & $Change $s
        $p = Join-Path $TestDrive ("spec-{0}.json" -f [guid]::NewGuid()); $s | ConvertTo-Json -Depth 8 | Set-Content $p; $p
    }
    # A tiny fake SharePoint site, held in a global so the module-scope mock can see it.
    function script:Reset-Site([object[]]$Lists = @(), [hashtable]$Columns = @{}) {
        $global:T14 = @{ Lists = [System.Collections.Generic.List[object]]::new(); Columns = $Columns; Calls = [System.Collections.Generic.List[object]]::new() }
        foreach ($l in $Lists) { $global:T14.Lists.Add($l) }
    }
    function script:Cols-From($Spec) {   # the columns Graph would return for a list made from the spec (plus built-ins)
        $b = ConvertTo-FDListBody -Spec $Spec
        @($b.columns | ForEach-Object { [pscustomobject]$_ }) + [pscustomobject]@{ name = 'Title' } + [pscustomobject]@{ name = 'Created' }
    }
}

Describe 'Spec file' {
    It 'loads the sample spec' {
        $spec.list.displayName | Should -Be 'M365 Apps Pulse Responses'
        @($spec.questions).Count | Should -Be 6
    }
    It 'refuses a site url that is not https, or has no path' {
        { Get-FDSpec -Path (New-Spec { param($s) $s.site.url = 'http://contoso.sharepoint.com/sites/x' }) } | Should -Throw '*https URL*'
        { Get-FDSpec -Path (New-Spec { param($s) $s.site.url = 'https://contoso.sharepoint.com' }) } | Should -Throw '*https URL*'
    }
    It 'refuses a column name that is not a plain internal name' {
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[0].column = 'Which dept' }) } | Should -Throw "*must start with a letter*"
    }
    It 'refuses a column that collides with a built-in or response column' {
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[0].column = 'Title' }) } | Should -Throw '*collides*'
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[1].column = 'ResponseId' }) } | Should -Throw '*collides*'
    }
    It 'refuses duplicate columns (case-insensitive)' {
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[1].column = 'department' }) } | Should -Throw '*used twice*'
    }
    It 'refuses an unknown question type' {
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[0].type = 'likert' }) } | Should -Throw "*type 'likert'*"
    }
    It 'refuses a choice question with fewer than two or duplicate choices' {
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[0].choices = @('Only') }) } | Should -Throw '*at least two choices*'
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[0].choices = @('A', 'A') }) } | Should -Throw '*duplicate choices*'
    }
    It 'refuses a rating without bounds and bounds that do not make sense' {
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[1].PSObject.Properties.Remove('max') }) } | Should -Throw '*needs min and max*'
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[1].min = 5 }) } | Should -Throw '*min >= max*'
    }
    It 'refuses a question without a title, a bad maxLength, and bad audit thresholds' {
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[0].title = '' }) } | Should -Throw '*needs a title*'
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions[3].maxLength = 0 }) } | Should -Throw '*maxLength*'
        { Get-FDSpec -Path (New-Spec { param($s) $s.audit.lowRating = 0 }) } | Should -Throw '*audit.lowRating*'
    }
    It 'refuses a missing file, no questions and no list name' {
        { Get-FDSpec -Path "$TestDrive/none.json" } | Should -Throw '*not found*'
        { Get-FDSpec -Path (New-Spec { param($s) $s.questions = @() }) } | Should -Throw '*at least one question*'
        { Get-FDSpec -Path (New-Spec { param($s) $s.list.displayName = '' }) } | Should -Throw '*list.displayName*'
    }
}

Describe 'Graph list body (facets as documented on Learn)' {
    BeforeAll { $script:body = ConvertTo-FDListBody -Spec $spec; $script:col = @{}; foreach ($c in $body.columns) { $col[$c['name']] = $c } }
    It 'is a genericList with the response columns first' {
        $body.list.template | Should -Be 'genericList'
        @($body.columns | Select-Object -First 3 | ForEach-Object { $_['name'] }) | Should -Be @('ResponseId', 'Responder', 'Submitted')
        $body.columns.Count | Should -Be 9
    }
    It 'makes ResponseId required, indexed and unique' {
        $col['ResponseId'].required | Should -BeTrue
        $col['ResponseId'].indexed | Should -BeTrue
        $col['ResponseId'].enforceUniqueValues | Should -BeTrue
    }
    It 'maps each question type to exactly one type facet' {
        $facets = 'text', 'choice', 'number', 'dateTime', 'boolean'
        foreach ($k in $col.Keys) { @($facets | Where-Object { $col[$k].Contains($_) }).Count | Should -Be 1 }
        $col['Department'].choice.displayAs | Should -Be 'dropDownMenu'
        $col['AppIssue'].choice.displayAs | Should -Be 'checkBoxes'
        $col['Rating'].number.minimum | Should -Be 1
        $col['Rating'].number.maximum | Should -Be 5
        $col['Comment'].text.allowMultipleLines | Should -BeTrue
        $col['ContactMe'].Contains('boolean') | Should -BeTrue
        $col['IncidentDate'].dateTime.format | Should -Be 'dateOnly'
        $col['Submitted'].dateTime.format | Should -Be 'dateTime'
    }
    It 'only uses enum values that Learn lists' {
        foreach ($c in $body.columns) {
            if ($c.Contains('choice')) { $c.choice.displayAs | Should -BeIn 'checkBoxes', 'dropDownMenu', 'radioButtons' }
            if ($c.Contains('number')) { $c.number.decimalPlaces | Should -BeIn 'automatic', 'none', 'one', 'two', 'three', 'four', 'five' }
            if ($c.Contains('dateTime')) { $c.dateTime.format | Should -BeIn 'dateOnly', 'dateTime'; $c.dateTime.displayAs | Should -BeIn 'default', 'friendly', 'standard' }
            if ($c.Contains('text') -and $c.text.Contains('textType')) { $c.text.textType | Should -BeIn 'plain', 'richText' }
        }
    }
    It 'serialises to JSON that Graph can take (keys survive a round trip)' {
        $j = $body | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $j.columns[3].choice.choices | Should -Be @('Finance', 'Sales', 'IT', 'Operations')
    }
    It 'maps number and text questions with their optional settings' {
        $c = ConvertTo-FDColumn -Question ([pscustomobject]@{ column = 'Score'; title = 't'; type = 'number'; min = 0; decimalPlaces = 'two' })
        $c.number.minimum | Should -Be 0; $c.number.decimalPlaces | Should -Be 'two'; $c.number.Contains('maximum') | Should -BeFalse
        (ConvertTo-FDColumn -Question ([pscustomobject]@{ column = 'Name'; title = 't'; type = 'text' })).text.maxLength | Should -Be 255
    }
}

Describe 'Flow mapping' {
    It 'lists every column the flow must fill, with its source' {
        $m = @(Get-FDFlowMap -Spec $spec)
        $m.Count | Should -Be 10
        ($m | Where-Object Column -eq 'ResponseId').From | Should -BeLike 'trigger*'
        ($m | Where-Object Column -eq 'Department').From | Should -BeLike "*'Which department are you in?'"
        ($m | Where-Object Column -eq 'AppIssue').Note | Should -BeLike 'multi-select*'
    }
}

Describe 'Compare-FDColumn' {
    It 'reports missing columns and ignores built-in ones' {
        $b = ConvertTo-FDListBody -Spec $spec
        $have = @(Cols-From $spec | Where-Object { $_.name -ne 'Rating' })
        $r = Compare-FDColumn -Wanted $b.columns -Existing $have
        @($r.Missing | ForEach-Object { $_['name'] }) | Should -Be @('Rating')
        $r.Drift.Count | Should -Be 0
    }
    It 'reports drift and never asks to change it' {
        $b = ConvertTo-FDListBody -Spec $spec
        $have = @(Cols-From $spec)
        ($have | Where-Object name -eq 'Department').choice.choices = @('Finance', 'Sales')
        ($have | Where-Object name -eq 'Rating').number.maximum = 10
        $r = Compare-FDColumn -Wanted $b.columns -Existing $have
        $r.Missing.Count | Should -Be 0
        ($r.Drift -join '|') | Should -BeLike '*Department: choices differ*'
        ($r.Drift -join '|') | Should -BeLike "*Rating: maximum is '10'*"
    }
    It 'reports a column that is of a different type' {
        $b = ConvertTo-FDListBody -Spec $spec
        $have = @(Cols-From $spec | ForEach-Object { if ($_.name -eq 'Comment') { [pscustomobject]@{ name = 'Comment'; number = @{} } } else { $_ } })
        (Compare-FDColumn -Wanted $b.columns -Existing $have).Drift | Should -Contain 'Comment: wanted a text column'
    }
}

Describe 'Set-FDList (Graph mocked with a small fake site)' {
    BeforeAll {
        Mock -ModuleName FormsData Invoke-MgGraphRequest {
            $global:T14.Calls.Add([pscustomobject]@{ Method = $Method; Uri = $Uri; Body = $Body })
            if ($Method -eq 'GET' -and $Uri -like '/v1.0/sites/contoso.sharepoint.com:*') { return @{ id = 'contoso.sharepoint.com,00000000-0000-0000-0000-000000000001,00000000-0000-0000-0000-000000000002' } }
            if ($Method -eq 'GET' -and $Uri -like '*/columns') { return @{ value = @($global:T14.Columns[($Uri -split '/')[-2]]) } }
            if ($Method -eq 'GET' -and $Uri -like '*/lists?*') {
                if ($Uri -like '*page2*') { return @{ value = @($global:T14.Lists | Select-Object -Skip 1) } }
                $r = @{ value = @($global:T14.Lists | Select-Object -First 1) }
                if ($global:T14.Lists.Count -gt 1) { $r['@odata.nextLink'] = '/v1.0/sites/x/lists?page2=1' }
                return $r
            }
            if ($Method -eq 'POST' -and $Uri -like '*/lists') { $o = $Body | ConvertFrom-Json -AsHashtable; $o['id'] = 'list-1'; $global:T14.Lists.Add([pscustomobject]$o); return $o }
            if ($Method -eq 'POST' -and $Uri -like '*/columns') { return @{} }
        }
    }
    It 'creates the list with all columns in one POST' {
        Reset-Site
        $r = Set-FDList -Spec $spec -Confirm:$false
        $r.Action | Should -Be 'Created'
        $call = $global:T14.Calls | Where-Object { $_.Method -eq 'POST' }
        $call.Uri | Should -Match '^/v1.0/sites/contoso.sharepoint.com,.*/lists$'
        $b = $call.Body | ConvertFrom-Json
        $b.displayName | Should -Be 'M365 Apps Pulse Responses'
        $b.columns.Count | Should -Be 9
    }
    It 'resolves the site by hostname and path' {
        Reset-Site
        $null = Set-FDList -Spec $spec -WhatIf
        ($global:T14.Calls | Select-Object -First 1).Uri | Should -Be '/v1.0/sites/contoso.sharepoint.com:/sites/mg-lab-forms'
    }
    It 'with -WhatIf writes nothing' {
        Reset-Site
        (Set-FDList -Spec $spec -WhatIf).Action | Should -Be 'WhatIf-Create'
        @($global:T14.Calls | Where-Object Method -ne 'GET').Count | Should -Be 0
    }
    It 'says Unchanged when the list already has every column' {
        Reset-Site @([pscustomobject]@{ id = 'list-1'; displayName = $spec.list.displayName }) @{ 'list-1' = @(Cols-From $spec) }
        (Set-FDList -Spec $spec -Confirm:$false).Action | Should -Be 'Unchanged'
        @($global:T14.Calls | Where-Object Method -eq 'POST').Count | Should -Be 0
    }
    It 'adds only the missing columns, one POST each' {
        Reset-Site @([pscustomobject]@{ id = 'list-1'; displayName = $spec.list.displayName }) @{ 'list-1' = @(Cols-From $spec | Where-Object { $_.name -notin 'Rating', 'ContactMe' }) }
        $r = Set-FDList -Spec $spec -Confirm:$false
        $r.Action | Should -Be 'ColumnsAdded'
        $r.Added | Should -Be 'Rating, ContactMe'
        $posts = @($global:T14.Calls | Where-Object Method -eq 'POST')
        $posts.Count | Should -Be 2
        $posts[0].Uri | Should -BeLike '*/lists/list-1/columns'
    }
    It 'with -WhatIf on an existing list names the columns it would add and sends nothing' {
        Reset-Site @([pscustomobject]@{ id = 'list-1'; displayName = $spec.list.displayName }) @{ 'list-1' = @(Cols-From $spec | Where-Object { $_.name -ne 'Rating' }) }
        $r = Set-FDList -Spec $spec -WhatIf
        $r.Action | Should -Be 'WhatIf-AddColumns'
        $r.Added | Should -Be 'WhatIf:Rating'
        @($global:T14.Calls | Where-Object Method -eq 'POST').Count | Should -Be 0
    }
    It 'reports drift on an existing column and leaves it alone' {
        $cols = @(Cols-From $spec); ($cols | Where-Object name -eq 'Department').choice.choices = @('Finance')
        Reset-Site @([pscustomobject]@{ id = 'list-1'; displayName = $spec.list.displayName }) @{ 'list-1' = $cols }
        $r = Set-FDList -Spec $spec -Confirm:$false
        $r.Action | Should -Be 'Unchanged'
        $r.Drift | Should -BeLike '*Department: choices differ*'
        @($global:T14.Calls | Where-Object { $_.Method -in 'PATCH', 'DELETE' }).Count | Should -Be 0
    }
    It 'finds the list on the second page of lists' {
        Reset-Site @([pscustomobject]@{ id = 'other'; displayName = 'Other' }, [pscustomobject]@{ id = 'list-1'; displayName = $spec.list.displayName }) @{ 'list-1' = @(Cols-From $spec) }
        (Set-FDList -Spec $spec -Confirm:$false).Id | Should -Be 'list-1'
    }
    It 'refuses two lists with the same name' {
        Reset-Site @([pscustomobject]@{ id = 'a'; displayName = $spec.list.displayName }, [pscustomobject]@{ id = 'b'; displayName = $spec.list.displayName })
        { Set-FDList -Spec $spec -Confirm:$false } | Should -Throw '*More than one list*'
    }
    It 'reads list items with expand=fields, across pages' {
        Mock -ModuleName FormsData Invoke-MgGraphRequest {
            $global:T14.Calls.Add([pscustomobject]@{ Method = $Method; Uri = $Uri })
            if ($Uri -like '/v1.0/sites/contoso.sharepoint.com:*') { return @{ id = 'site-1' } }
            if ($Uri -like '*page2*') { return @{ value = @(@{ id = '3'; fields = @{ ResponseId = 3 } }) } }
            if ($Uri -like '*lists?`$select*') { return @{ value = @(@{ id = 'list-1'; displayName = 'M365 Apps Pulse Responses' }) } }
            if ($Uri -like '*/items?expand=fields') { return @{ value = @(@{ id = '1'; fields = @{ ResponseId = 1 } }, @{ id = '2'; fields = @{ ResponseId = 2 } }); '@odata.nextLink' = '/v1.0/sites/site-1/lists/list-1/items?page2=1' } }
        }
        Reset-Site
        $r = @(Get-FDResponse -SiteUrl $spec.site.url -ListName $spec.list.displayName)
        $r.Count | Should -Be 3
        ($global:T14.Calls | Where-Object Uri -like '*items?expand=fields').Uri | Should -Be '/v1.0/sites/site-1/lists/list-1/items?expand=fields'
    }
    It 'fails clearly when the list does not exist' {
        Reset-Site
        Mock -ModuleName FormsData Invoke-MgGraphRequest { if ($Uri -like '/v1.0/sites/contoso*') { @{ id = 'site-1' } } else { @{ value = @() } } }
        { Get-FDResponse -SiteUrl $spec.site.url -ListName 'Nope' } | Should -Throw "*Expected one list called 'Nope', found 0*"
    }
}

Describe 'Response findings (fictional list items in the shape Graph returns)' {
    BeforeAll { $script:f = @(Get-FDResponseFinding -Items $items -Spec $spec) }
    It 'finds the nine planted problems and nothing else' { $f.Count | Should -Be 9 }
    It 'flags a duplicate ResponseId as High' { ($f | Where-Object Type -eq 'DuplicateResponseId').Severity | Should -Be 'High'; ($f | Where-Object Type -eq 'DuplicateResponseId').ResponseId | Should -Be '3' }
    It 'flags a required answer that is empty' { ($f | Where-Object Type -eq 'MissingRequired').ResponseId | Should -Be 4 }
    It 'flags a value that is not one of the choices' { ($f | Where-Object Type -eq 'InvalidChoice').Detail | Should -BeLike "*'Legal'*" }
    It 'flags a rating outside the bounds' { ($f | Where-Object Type -eq 'OutOfRange').Detail | Should -BeLike '*7*1..5*' }
    It 'flags a low rating with no comment' { @($f | Where-Object Type -eq 'LowRatingNoComment').Count | Should -Be 2 }
    It 'flags a double submit inside the window, and not outside it' {
        ($f | Where-Object Type -eq 'PossibleDoubleSubmit').ResponseId | Should -Be 9
        $s2 = Get-FDSpec -Path (New-Spec { param($s) $s.audit.duplicateWindowMinutes = 1 })
        @(Get-FDResponseFinding -Items $items -Spec $s2 | Where-Object Type -eq 'PossibleDoubleSubmit').Count | Should -Be 0
    }
    It 'reports an anonymous response as Info' { ($f | Where-Object Type -eq 'AnonymousResponder').Severity | Should -Be 'Info' }
    It 'reports the gap in response ids with the caveat' { ($f | Where-Object Type -eq 'ResponseIdGap').ResponseId | Should -Be '7'; ($f | Where-Object Type -eq 'ResponseIdGap').Detail | Should -BeLike '*deleted in Forms*' }
    It 'sorts High first' { $f[0].Severity | Should -Be 'High' }
    It 'accepts a clean list' {
        $clean = @($items[0], $items[2])
        @(Get-FDResponseFinding -Items $clean -Spec $spec | Where-Object { $_.Type -ne 'ResponseIdGap' }).Count | Should -Be 0
    }
    It 'reads a multi-select stored as a plain string too' {
        $one = [pscustomobject]@{ fields = [pscustomobject]@{ ResponseId = 1; Responder = 'a'; Submitted = '2026-11-23T09:00:00Z'; Department = 'IT'; Rating = 3; AppIssue = 'Excel'; Comment = 'x' } }
        @(Get-FDResponseFinding -Items @($one) -Spec $spec).Count | Should -Be 0
    }
}

Describe 'Summary and markdown' {
    BeforeAll { $script:sum = Get-FDSummary -Items $items -Spec $spec }
    It 'counts responses, choices and ratings' {
        $sum.Total | Should -Be 9
        ($sum.Questions | Where-Object Column -eq 'Department').Counts.IT | Should -Be 3
        ($sum.Questions | Where-Object Column -eq 'AppIssue').Counts.Outlook | Should -Be 2
        ($sum.Questions | Where-Object Column -eq 'Rating').Counts['5'] | Should -Be 3
        ($sum.Questions | Where-Object Column -eq 'Rating').Average | Should -Be 4
        ($sum.Questions | Where-Object Column -eq 'ContactMe').Yes | Should -Be 2
    }
    It 'counts responses per day' { ($sum.PerDay | Where-Object Day -eq '2026-11-24').Responses | Should -Be 5 }
    It 'counts answered questions (empty and missing do not count)' { ($sum.Questions | Where-Object Column -eq 'Department').Answered | Should -Be 8; ($sum.Questions | Where-Object Column -eq 'Comment').Answered | Should -Be 7 }
    It 'renders a table sorted High first' {
        $md = ConvertTo-FDMarkdown -Title 'T' -Summary $sum -Findings (Get-FDResponseFinding -Items $items -Spec $spec) -Asof 'x'
        $md | Should -BeLike '*9 response(s)*'
        $md | Should -BeLike '*9 data-quality finding(s):** 1 High / 3 Medium / 3 Low / 2 Info*'
        $md.IndexOf('| High |') | Should -BeLessThan $md.IndexOf('| Medium |')
    }
    It 'handles no responses' {
        $e = Get-FDSummary -Items @() -Spec $spec
        $e.Total | Should -Be 0
        (ConvertTo-FDMarkdown -Title 'T' -Summary $e) | Should -BeLike '*0 response(s)*'
    }
}
