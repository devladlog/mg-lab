#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# The tenant tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong
# parameter name or type fails the test). They are skipped when PnP.PowerShell isn't installed.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
}

BeforeAll {
    $script:src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgSearchMeta.psm1') -Force
    $script:termSet = Import-MgJson -Path (Join-Path $src 'search' 'purchasing-categories.termset.json')
    $script:plan = Import-MgJson -Path (Join-Path $src 'search' 'search-plan.json')
    $script:tests = Import-MgJson -Path (Join-Path $src 'search' 'search-tests.json')
    $script:badPlan = Import-MgJson -Path (Join-Path $src 'bad' 'bad-search-plan.json')
    $script:badQueries = Import-MgJson -Path (Join-Path $src 'bad' 'bad-queries.json')
    $script:today = [datetime]'2026-12-01'
    $script:site = 'https://contoso.sharepoint.com/sites/Purchasing'

    function Rules($f) { @($f | ForEach-Object Rule) }
    function Copy-Json($o) { $o | ConvertTo-Json -Depth 30 | ConvertFrom-Json -Depth 30 }
    function Kql([string]$q) { @(Test-MgKql -Query $q -Plan $plan) }
    function Live([string]$Name, [string[]]$Aliases, [string[]]$Mappings) { [pscustomobject]@{ Name = $Name; Pid = '0'; Type = 'Text'; Aliases = $Aliases; Mappings = $Mappings } }
    function Good-Mappings {
        Live 'RefinableString00' @('PurchSupplier') @('ows_q_TEXT_Supplier')
        Live 'RefinableString01' @('PurchDept') @('ows_PurchDepartment')
        Live 'RefinableDate00' @('PurchExpiry') @('ows_q_DATE_ExpiryDate')
        Live 'RefinableDate01' @('PurchInvoiceDate') @('ows_q_DATE_InvoiceDate')
    }
}

Describe 'Automatically created properties (Learn naming convention)' {
    It "reproduces Learn's examples" {
        $a = Get-MgAutoPropertyName -Name 'ContosoColor' -Type Text
        $a.Crawled | Should -Be 'ows_q_TEXT_ContosoColor'; $a.Managed | Should -Be 'ContosoColorOWSTEXT'
        $a = Get-MgAutoPropertyName -Name 'ContosoWeight' -Type Number
        $a.Crawled | Should -Be 'ows_q_NMBR_ContosoWeight'; $a.Managed | Should -Be 'ContosoWeightOWSNMBR'
        (Get-MgAutoPropertyName -Name 'Germanäö' -Type Text).Managed | Should -Be 'GermanOWSTEXT'
        (Get-MgAutoPropertyName -Name 'Site_Column#' -Type Text).Crawled | Should -Be 'ows_q_TEXT_Site_Column#'
        (Get-MgAutoPropertyName -Name 'Site_Column#' -Type Text).Managed | Should -Be 'SiteColumnOWSTEXT'
        (Get-MgAutoPropertyName -Name 'ProductCatalogItemCategory' -Type TaxonomyFieldType).Managed | Should -Be 'owstaxIdProductCatalogItemCategory'
        (Get-MgAutoPropertyName -Name 'Comments' -Type Note).Crawled | Should -Be 'ows_r_MTXT_Comments'
        (Get-MgAutoPropertyName -Name 'ExpiryDate' -Type DateTime).ManagedType | Should -Be 'Text'
    }

    It 'has no automatic property for lookups' {
        { Get-MgAutoPropertyName -Name 'Order' -Type Lookup } | Should -Throw '*No automatically created property*'
    }
}

Describe 'Default unused managed properties (Learn table)' {
    It 'knows the ranges, types and which ones refine' {
        (Get-MgManagedPropertyInfo 'RefinableString219').Type | Should -Be 'Text'
        Get-MgManagedPropertyInfo 'RefinableString220' | ForEach-Object OutOfRange | Should -BeTrue
        (Get-MgManagedPropertyInfo 'RefinableDate19').Type | Should -Be 'DateTime'
        (Get-MgManagedPropertyInfo 'RefinableDateSingle04').Refinable | Should -BeTrue
        (Get-MgManagedPropertyInfo 'RefinableStringWbOffFirst49').Type | Should -Be 'Text'
        (Get-MgManagedPropertyInfo 'Date09').Refinable | Should -BeFalse
        (Get-MgManagedPropertyInfo 'Int49').Type | Should -Be 'Integer'
        Get-MgManagedPropertyInfo 'Supplier' | Should -BeNullOrEmpty
        Get-MgManagedPropertyInfo 'RefinableString050' | Should -BeNullOrEmpty
    }
}

Describe 'Test-MgTermSet' {
    It 'the purchasing categories are clean, and Facilities|Cleaning resolves to its fixed ID' {
        @(Test-MgTermSet -TermSet $termSet) | Should -HaveCount 0
        (Resolve-MgTermPath -TermSet $termSet -Path 'Facilities|Cleaning').Id | Should -Be '5f0c2b1e-7a4d-4c39-9e61-2d8a4b7c1e11'
        Resolve-MgTermPath -TermSet $termSet -Path 'Cleaning' | Should -BeNullOrEmpty
    }

    It 'TX002: the same label twice at one level, ignoring case; the same label under two parents is fine' {
        $t = Copy-Json $termSet
        $t.terms[0].children += [pscustomobject]@{ name = 'cleaning'; id = [guid]::NewGuid().ToString() }
        $t.terms[1].children += [pscustomobject]@{ name = 'Maintenance'; id = [guid]::NewGuid().ToString() }
        Rules (Test-MgTermSet -TermSet $t) | Should -Be @('TX002')
    }

    It 'TX001 and TX003: bad, empty or duplicate IDs and empty labels' {
        $t = Copy-Json $termSet
        $t.terms[0].id = 'facilities'
        $t.terms[1].id = $t.terms[2].id
        $t.terms[3].name = ' '
        $f = @(Test-MgTermSet -TermSet $t)
        @($f | Where-Object Rule -eq 'TX001') | Should -HaveCount 2
        Rules $f | Should -Contain 'TX003'
    }
}

Describe 'Test-MgSearchPlan' {
    It 'the purchasing plan is clean' {
        @(Test-MgSearchPlan -Plan $plan -TermSet $termSet) | Should -HaveCount 0
    }

    It 'finds every mistake in the bad plan: 5 errors, 3 warnings' {
        $f = @(Test-MgSearchPlan -Plan $badPlan)
        @($f | Where-Object Severity -eq 'Error') | Should -HaveCount 5
        @($f | Where-Object Severity -eq 'Warning') | Should -HaveCount 3
        Rules $f | Sort-Object -Unique | Should -Be @('SP001', 'SP002', 'SP003', 'SP004', 'SP005', 'SP006', 'SP007')
        ($f | Where-Object Rule -eq 'SP002').Message | Should -BeLike '*dates would compare as text*'
    }

    It 'SP005: an alias equal to the automatic property of the column' {
        $p = Copy-Json $plan; $p.mappings[0].alias = 'SupplierOWSTEXT'
        Rules (Test-MgSearchPlan -Plan $p) | Should -Be @('SP005')
    }

    It 'TX004 and TX005: a category that is not a term, a wrong term set path, a term set closed for tagging' {
        $p = Copy-Json $plan
        $p.supplierCategories.Fabrikam = 'Facilities|Window Cleaning'
        $p.categoryColumn.termSetPath = 'Contoso|Purchasing Categories'
        $t = Copy-Json $termSet; $t.termSet.availableForTagging = $false
        Rules (Test-MgSearchPlan -Plan $p -TermSet $t) | Sort-Object | Should -Be @('TX004', 'TX004', 'TX005')
    }
}

Describe 'ConvertTo-MgKql (tokens)' {
    It 'resolves site, dates, content types and terms' {
        $q = ConvertTo-MgKql -Template 'ContentTypeId:{ct:Contract}* PurchExpiry<={today+60d} PurchExpiry>{today-1d} owstaxIdPurchCategory:"GPP|#{term:Facilities}" Path:"{site}"' `
            -Plan $plan -TermSet $termSet -SiteUrl $site -Today $today
        $q | Should -Be 'ContentTypeId:0x010100D5F0B586695B489A84366F90C59E924901* PurchExpiry<=2027-01-30 PurchExpiry>2026-11-30 owstaxIdPurchCategory:"GPP|#5f0c2b1e-7a4d-4c39-9e61-2d8a4b7c1e10" Path:"https://contoso.sharepoint.com/sites/Purchasing"'
    }

    It 'refuses unknown tokens, content types and terms' {
        { ConvertTo-MgKql -Template '{tomorrow}' -Plan $plan } | Should -Throw '*Unknown token*'
        { ConvertTo-MgKql -Template '{ct:Order}' -Plan $plan } | Should -Throw '*Unknown content type*'
        { ConvertTo-MgKql -Template '{term:Travel}' -Plan $plan -TermSet $termSet } | Should -Throw '*Unknown term*'
    }
}

Describe 'Test-MgKql (KQL syntax reference)' {
    It "accepts Learn's own example queries" {
        $ok = @(
            'author:"John Smith" AND filetype:docx'
            'title:"Advanced Sear*"'
            'LastModifiedTime>=2019-01-01 AND LastModifiedTime<=2019-04-26'
            'LastModifiedTime="this year"'
            '(DepartmentId:* OR RelatedHubSites:*) AND contentclass:sts_site NOT IsHubSite:true'
            '"acquisition" NEAR(n=3) "debt"'
            'title:((Advanced OR Search OR Query) -"Advanced Search Query")'
            'federat* search'
        )
        foreach ($q in $ok) { Kql $q | Should -HaveCount 0 -Because $q }
    }

    It 'finds the mistake in each real-world query' {
        $expected = @('KQ003', 'KQ002', 'KQ005', 'KQ007', 'KQ006', 'KQ004', 'KQ009')
        for ($i = 0; $i -lt $badQueries.tests.Count; $i++) {
            Rules (Kql $badQueries.tests[$i].query) | Should -Be @($expected[$i]) -Because $badQueries.tests[$i].name
        }
    }

    It 'KQ003: white space before the operator too' {
        Rules (Kql 'author :"John Smith"') | Should -Be @('KQ003')
    }

    It 'KQ005: a range on a date alias is fine, on a text alias it is not' {
        Kql 'PurchExpiry:2026-01-01..2026-12-31' | Should -HaveCount 0
        Rules (Kql 'PurchSupplier:A..F') | Should -Be @('KQ005')
    }

    It 'KQ001, KQ008, KQ009, KQ010' {
        Rules (Kql 'AND') | Should -Be @('KQ001')
        Rules (Kql '') | Should -Be @('KQ001')
        Rules (Kql ('a' * 2100)) | Should -Be @('KQ008')
        (Kql ('a' * 2100)).Severity | Should -Be 'Warning'
        (Kql ('a' * 4100)).Severity | Should -Be 'Error'
        Rules (Kql '(PurchSupplier:Fabrikam OR PurchSupplier:Northwind') | Should -Be @('KQ009')
        Rules (Kql 'Title=Fabrik*') | Should -Be @('KQ010')
    }

    It 'every query in the search tests is valid except the lint-only gotcha' {
        foreach ($t in $tests.tests) {
            $f = @(Test-MgKql -Query (ConvertTo-MgKql -Template $t.query -Plan $plan -TermSet $termSet -Today $today) -Plan $plan)
            if ($t.PSObject.Properties['lintOnly']) { Rules $f | Should -Be @('KQ005') } else { $f | Should -HaveCount 0 -Because $t.name }
        }
    }
}

Describe 'Test-MgSearchMapping (site collection schema)' {
    It 'accepts the plan mapped with either documented crawled property name' {
        @(Test-MgSearchMapping -Plan $plan -Mappings @(Good-Mappings)) | Should -HaveCount 0
    }

    It 'SM001 missing mapping, SM002 missing alias, SM003 extra crawled property' {
        $live = @(Good-Mappings)
        $live = @($live | Where-Object Name -ne 'RefinableDate01')
        $live[0].Aliases = @()
        $live[2].Mappings = @('ows_q_DATE_ExpiryDate', 'ows_q_DATE_InvoiceDate')
        Rules (Test-MgSearchMapping -Plan $plan -Mappings $live) | Sort-Object | Should -Be @('SM001', 'SM002', 'SM003')
    }

    It 'an empty schema means nothing is mapped' {
        @(Test-MgSearchMapping -Plan $plan -Mappings @()) | Should -HaveCount 4
    }
}

Describe 'Test-MgSearchResult' {
    It 'checks counts, file names and refiner values' {
        $t = $tests.tests | Where-Object name -eq 'Refine by supplier'
        $rows = 1..5 | ForEach-Object { @{ Filename = "f$_.txt"; Path = "$site/SupplierDocuments/f$_.txt" } }
        $ref = 'Adventure Works', 'Fabrikam', 'Northwind Traders', 'Tailspin Toys' | ForEach-Object { [pscustomobject]@{ RefinerName = 'RefinableString00'; RefinementName = $_ } }
        (Test-MgSearchResult -Test $t -Result ([pscustomobject]@{ Rows = $rows; Refiners = $ref })).Passed | Should -BeTrue
        $r = Test-MgSearchResult -Test $t -Result ([pscustomobject]@{ Rows = $rows[0..2]; Refiners = $ref[0..1] })
        $r.Passed | Should -BeFalse
        $r.Problems | Should -HaveCount 3
    }

    It 'falls back to the file name in Path' {
        $t = $tests.tests | Where-Object name -eq 'Expired contracts'
        $rows = @(@{ Path = "$site/SupplierDocuments/Tailspin%20Toys/CTR-2025-0107%20Tailspin%20Toys%20until%202026-11-21.txt" })
        (Test-MgSearchResult -Test $t -Result ([pscustomobject]@{ Rows = $rows; Refiners = @() })).Passed | Should -BeTrue
    }
}

Describe 'Invoke-SearchMetadata.ps1 (offline modes)' {
    It 'lints the bad plan: 5 errors, 3 warnings' {
        $out = & (Join-Path $src 'Invoke-SearchMetadata.ps1') -PlanPath (Join-Path $src 'bad' 'bad-search-plan.json') 6>&1 | Out-String
        $out | Should -BeLike '*5 error(s), 3 warning(s)*'
    }

    It 'lints the good plan, the term set and every test query' {
        $out = & (Join-Path $src 'Invoke-SearchMetadata.ps1') -PlanPath (Join-Path $src 'search' 'search-plan.json') `
            -TermSetPath (Join-Path $src 'search' 'purchasing-categories.termset.json') -TestsPath (Join-Path $src 'search' 'search-tests.json') -Today $today 6>&1 | Out-String
        $out | Should -BeLike '*0 error(s), 0 warning(s)*'
        $out | Should -BeLike '*GPP|#5f0c2b1e-7a4d-4c39-9e61-2d8a4b7c1e10*'
    }
}

Describe 'Tenant functions (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
    }

    It 'creates the term group, the term set, 5 terms and 9 child terms with their fixed IDs' {
        Mock -ModuleName MgSearchMeta Get-PnPTermGroup { throw 'not found' }
        Mock -ModuleName MgSearchMeta Get-PnPTermSet { throw 'not found' }
        Mock -ModuleName MgSearchMeta Get-PnPTerm { throw 'not found' }
        Mock -ModuleName MgSearchMeta New-PnPTermGroup { }
        Mock -ModuleName MgSearchMeta New-PnPTermSet { }
        Mock -ModuleName MgSearchMeta New-PnPTerm { }
        Mock -ModuleName MgSearchMeta Add-PnPTermToTerm { }
        $steps = @(Invoke-MgTaxonomyProvisioning -TermSet $termSet)
        Should -Invoke -ModuleName MgSearchMeta New-PnPTermGroup -Times 1 -Exactly -ParameterFilter { $Name -eq 'Contoso Purchasing' -and $Id -eq [guid]'5f0c2b1e-7a4d-4c39-9e61-2d8a4b7c1e01' }
        Should -Invoke -ModuleName MgSearchMeta New-PnPTermSet -Times 1 -Exactly -ParameterFilter { $Name -eq 'Purchasing Categories' -and $Lcid -eq 1033 }
        Should -Invoke -ModuleName MgSearchMeta New-PnPTerm -Times 5 -Exactly
        Should -Invoke -ModuleName MgSearchMeta Add-PnPTermToTerm -Times 9 -Exactly
        Should -Invoke -ModuleName MgSearchMeta Add-PnPTermToTerm -Times 1 -Exactly -ParameterFilter {
            $Name -eq 'Cleaning' -and $ParentTermId -eq [guid]'5f0c2b1e-7a4d-4c39-9e61-2d8a4b7c1e10' -and $Id -eq [guid]'5f0c2b1e-7a4d-4c39-9e61-2d8a4b7c1e11' }
        $steps | Should -HaveCount 16
    }

    It 'is idempotent and -WhatIf writes nothing' {
        Mock -ModuleName MgSearchMeta Get-PnPTermGroup { [pscustomobject]@{ Name = 'Contoso Purchasing' } }
        Mock -ModuleName MgSearchMeta Get-PnPTermSet { [pscustomobject]@{ Name = 'Purchasing Categories' } }
        Mock -ModuleName MgSearchMeta Get-PnPTerm { [pscustomobject]@{ Name = 'x' } }
        foreach ($c in 'New-PnPTermGroup', 'New-PnPTermSet', 'New-PnPTerm', 'Add-PnPTermToTerm') { Mock -ModuleName MgSearchMeta $c { throw 'should not write' } }
        @(Invoke-MgTaxonomyProvisioning -TermSet $termSet) | Should -HaveCount 0
        Mock -ModuleName MgSearchMeta Get-PnPTerm { throw 'not found' }
        @(Invoke-MgTaxonomyProvisioning -TermSet $termSet -WhatIf) | Should -HaveCount 14
    }

    It 'adds the Category site column bound to the term set and pushes it to the content type children' {
        Mock -ModuleName MgSearchMeta Get-PnPField { $null }
        Mock -ModuleName MgSearchMeta Add-PnPTaxonomyField { }
        Mock -ModuleName MgSearchMeta Add-PnPFieldToContentType { }
        $steps = @(Invoke-MgCategoryColumn -Plan $plan)
        Should -Invoke -ModuleName MgSearchMeta Add-PnPTaxonomyField -Times 1 -Exactly -ParameterFilter {
            $InternalName -eq 'PurchCategory' -and $TermSetPath -eq 'Contoso Purchasing|Purchasing Categories' -and $Id -eq [guid]'9c3e7d52-0b8a-4f6e-a1d4-6e2f8b9c0a31' -and -not $List }
        Should -Invoke -ModuleName MgSearchMeta Add-PnPFieldToContentType -Times 1 -Exactly -ParameterFilter { "$ContentType" -eq 'Purchasing Document' -and $UpdateChildren -eq $true }
        $steps | Should -HaveCount 2
    }

    It 'tags files by supplier, skips folders, unknown suppliers and files already tagged' {
        Mock -ModuleName MgSearchMeta Get-PnPListItem {
            @{ Id = 1; FileLeafRef = 'Fabrikam'; FSObjType = 1; Supplier = 'Fabrikam'; PurchCategory = $null }
            @{ Id = 2; FileLeafRef = 'CTR-2026-0042 Fabrikam until 2026-12-31.txt'; FSObjType = 0; Supplier = 'Fabrikam'; PurchCategory = $null }
            @{ Id = 3; FileLeafRef = 'INV-10022 Northwind Traders 2026-11-16.txt'; FSObjType = 0; Supplier = 'Northwind Traders'; PurchCategory = [pscustomobject]@{ TermGuid = '5f0c2b1e-7a4d-4c39-9e61-2d8a4b7c1e21' } }
            @{ Id = 4; FileLeafRef = 'scan_0001.txt'; FSObjType = 0; Supplier = $null; PurchCategory = $null }
            @{ Id = 5; FileLeafRef = 'CTR-2026-0099 Contoso Pharma.txt'; FSObjType = 0; Supplier = 'Contoso Pharma'; PurchCategory = $null }
        }
        Mock -ModuleName MgSearchMeta Set-PnPListItem { }
        $steps = @(Invoke-MgCategoryTagging -Plan $plan -TermSet $termSet)
        Should -Invoke -ModuleName MgSearchMeta Set-PnPListItem -Times 1 -Exactly
        Should -Invoke -ModuleName MgSearchMeta Set-PnPListItem -Times 1 -Exactly -ParameterFilter {
            $Values.PurchCategory -eq '5f0c2b1e-7a4d-4c39-9e61-2d8a4b7c1e11' -and "$UpdateType" -eq 'SystemUpdate' }
        @($steps | Where-Object Action -eq 'Skip') | Should -HaveCount 2
    }

    It 'reads the site collection mappings with the documented output format' {
        Mock -ModuleName MgSearchMeta Get-PnPSearchConfiguration { Good-Mappings }
        $live = @(Get-MgSiteSearchMapping)
        Should -Invoke -ModuleName MgSearchMeta Get-PnPSearchConfiguration -Times 1 -Exactly -ParameterFilter { "$Scope" -eq 'Site' -and "$OutputFormat" -eq 'ManagedPropertyMappings' }
        @(Test-MgSearchMapping -Plan $plan -Mappings $live) | Should -HaveCount 0
    }

    It 'runs the search tests with Submit-PnPSearchQuery and reads results and refiners' {
        Mock -ModuleName MgSearchMeta Submit-PnPSearchQuery {
            $rows = switch -Wildcard ($Query) {
                'PurchSupplier:"Fabrikam"*' { @(@{ Filename = 'CTR-2026-0042 Fabrikam until 2026-12-31.txt' }, @{ Filename = 'INV-10021 Fabrikam 2026-11-11.txt' }) }
                '*PurchExpiry>=*' { @(@{ Filename = 'CTR-2026-0042 Fabrikam until 2026-12-31.txt' }) }
                '*PurchExpiry<2026*' { @(@{ Filename = 'CTR-2025-0107 Tailspin Toys until 2026-11-21.txt' }) }
                '*NOT PurchExpiry*' { @(@{ Filename = 'CTR-2026-0050 Adventure Works.txt' }) }
                'owstaxId*' { @(@{ Filename = 'CTR-2026-0042 Fabrikam until 2026-12-31.txt' }, @{ Filename = 'INV-10021 Fabrikam 2026-11-11.txt' }) }
                default { 1..6 | ForEach-Object { @{ Filename = "f$_.txt" } } }
            }
            [pscustomobject]@{ TableType = 'RelevantResults'; TotalRows = $rows.Count; ResultRows = $rows }
            if ($Refiners) {
                [pscustomobject]@{ TableType = 'RefinementResults'; ResultRows = @('Adventure Works', 'Fabrikam', 'Northwind Traders', 'Tailspin Toys' | ForEach-Object {
                            @{ RefinerName = 'RefinableString00'; RefinementName = $_; RefinementCount = 1 } }) }
            }
        }
        $results = @(Invoke-MgSearchTest -Tests $tests -Plan $plan -TermSet $termSet -SiteUrl $site -Today $today)
        $results | Should -HaveCount 6
        @($results | Where-Object { -not $_.Passed }) | Should -HaveCount 0
        Should -Invoke -ModuleName MgSearchMeta Submit-PnPSearchQuery -Times 1 -Exactly -ParameterFilter { $Refiners -eq 'RefinableString00' -and $SelectProperties -contains 'Filename' }
        Should -Invoke -ModuleName MgSearchMeta Submit-PnPSearchQuery -Times 0 -ParameterFilter { $Query -like '*OWSDATE*' }
    }
}
