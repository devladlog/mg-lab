#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# The tenant tests mock the real PnP.PowerShell cmdlets (Pester copies their parameter metadata, so a wrong
# parameter name or type fails the test). They are skipped when PnP.PowerShell isn't installed.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
}

BeforeAll {
    $src = Join-Path $PSScriptRoot '..' 'src'
    Import-Module (Join-Path $src 'MgDocMgmt.psm1') -Force
    $script:design = Import-MgJson -Path (Join-Path $src 'docmgmt' 'supplier-documents.json')
    $script:plan = Import-MgJson -Path (Join-Path $src 'docmgmt' 'filing-plan.json')
    $script:bad = Import-MgJson -Path (Join-Path $src 'bad' 'legacy-documents.json')
    $script:today = [datetime]'2026-12-01'
    $script:samples = Join-Path $TestDrive 'samples'
    & (Join-Path $src 'New-SampleDocuments.ps1') -Path $samples -Today $today | Out-Null

    function Rules($f) { @($f | ForEach-Object Rule) }
    function Copy-Design($d) { $d | ConvertTo-Json -Depth 30 | ConvertFrom-Json -Depth 30 }
    function Item([string]$Name, [string]$Ct = 'Contract', [hashtable]$Values = @{}, [string]$CheckedOutTo, [datetime]$Modified = $today, [string]$DocId = 'CONTOSO-1-1', [switch]$Folder) {
        $v = @{ Supplier = 'Fabrikam'; PurchDepartment = 'Purchasing'; ContractNumber = '2026-0001'; ExpiryDate = $today.AddDays(365) }
        foreach ($k in $Values.Keys) { $v[$k] = $Values[$k] }
        [pscustomobject]@{ Name = $Name; Folder = 'SupplierDocuments/Fabrikam'; IsFolder = [bool]$Folder; ContentType = $Ct; Values = $v
            CheckedOutTo = $CheckedOutTo; Modified = $Modified; DocId = $DocId }
    }
    function Audit([object[]]$Items) { Test-MgDocumentItem -Items $Items -Design $design -Library 'Supplier Documents' -Today $today }
}

Describe 'Content type IDs (Learn rules)' {
    It 'New-MgContentTypeId: parent + 00 + GUID by default, parent + two hex digits on request' {
        $g = [guid]'d5f0b586-695b-489a-8436-6f90c59e9249'
        New-MgContentTypeId -ParentId '0x0101' -Guid $g | Should -Be '0x010100D5F0B586695B489A84366F90C59E9249'
        New-MgContentTypeId -ParentId '0x010100D5F0B586695B489A84366F90C59E9249' -Suffix '01' | Should -Be '0x010100D5F0B586695B489A84366F90C59E924901'
        { New-MgContentTypeId -ParentId '0x0101' -Suffix '00' } | Should -Throw
    }

    It "accepts Learn's own examples" {
        @(Test-MgContentTypeId -Id '0x0101000728167cd9c94899925ba69c4af6743e' -ParentId '0x0101') | Should -HaveCount 0
        @(Test-MgContentTypeId -Id '0x0101000728167cd9c94899925ba69c4af6743e01' -ParentId '0x0101000728167cd9c94899925ba69c4af6743e') | Should -HaveCount 0
        @(Test-MgContentTypeId -Id '0x0100A33D9AD9805788419BDAAC2CCB37509F' -ParentId '0x01') | Should -HaveCount 0
        # a list content type: site content type + 00 + GUID
        @(Test-MgContentTypeId -Id '0x0100A33D9AD9805788419BDAAC2CCB37509F006454F8883E8BA648A632E5ACB47CAD9B' -ParentId '0x0100A33D9AD9805788419BDAAC2CCB37509F') | Should -HaveCount 0
    }

    It 'rejects malformed IDs' {
        foreach ($id in '0x0101Contract', '0x101', '0101', '0x') { Rules (Test-MgContentTypeId -Id $id) | Should -Be @('DM001') -Because $id }
    }

    It '1,024 characters is the maximum' {
        $ok = '0x' + ('01' * 511)        # 1,024 characters
        @(Test-MgContentTypeId -Id $ok) | Should -HaveCount 0
        Rules (Test-MgContentTypeId -Id ($ok + '01')) | Should -Be @('DM002')
    }

    It 'checks lineage and the suffix' {
        Rules (Test-MgContentTypeId -Id '0x0100A33D9AD9805788419BDAAC2CCB37509F01' -ParentId '0x010105') | Should -Be @('DM003')
        Rules (Test-MgContentTypeId -Id '0x0101' -ParentId '0x0101') | Should -Be @('DM003')
        Rules (Test-MgContentTypeId -Id '0x01010500' -ParentId '0x010105') | Should -Be @('DM004')
        Rules (Test-MgContentTypeId -Id '0x01010500ABCD' -ParentId '0x010105') | Should -Be @('DM004')
        (Test-MgContentTypeId -Id '0x010105' -ParentId '0x0101').Severity | Should -Be 'Warning'
        @(Test-MgContentTypeId -Id '0x01010501' -ParentId '0x010105') | Should -HaveCount 0
    }
}

Describe 'Test-MgDocDesign' {
    It 'the supplier design with its filing plan has no findings' {
        @(Test-MgDocDesign -Design $design -Plan $plan) | Should -HaveCount 0
        @(Test-MgFilingPlan -Plan $plan -Design $design) | Should -HaveCount 0
    }

    It 'without the plan, only the required fields nobody fills are reported (Department has a default)' {
        $f = @(Test-MgDocDesign -Design $design)
        $f | Should -HaveCount 7
        Rules $f | Sort-Object -Unique | Should -Be @('DM013')
        $f.Message | Where-Object { $_ -match 'PurchDepartment' } | Should -BeNullOrEmpty
    }

    It 'the legacy design has every planted problem: 8 errors, 7 warnings' {
        $f = @(Test-MgDocDesign -Design $bad)
        @($f | Where-Object Severity -eq 'Error') | Should -HaveCount 8
        @($f | Where-Object Severity -eq 'Warning') | Should -HaveCount 7
        foreach ($r in 'DM001', 'DM003', 'DM004', 'DM005', 'DM006', 'DM007', 'DM008', 'DM009', 'DM010', 'DM011', 'DM012', 'DM013', 'DM014', 'DM015') { Rules $f | Should -Contain $r }
    }

    It 'a document set needs the Document Sets feature' {
        $d = Copy-Design $design; $d.features.documentSets = $false
        Rules (Test-MgDocDesign -Design $d -Plan $plan) | Should -Be @('DM008')
    }

    It 'Document IDs plus content type hub: warn' {
        $d = Copy-Design $design; $d.contentTypeHub = $true
        Rules (Test-MgDocDesign -Design $d -Plan $plan) | Should -Be @('DM011')
    }

    It 'require check-out: warn (it blocks co-authoring)' {
        $d = Copy-Design $design; $d.libraries[0].requireCheckout = $true
        Rules (Test-MgDocDesign -Design $d -Plan $plan) | Should -Be @('DM010')
    }

    It 'inherits fields from parent content types; required wins' {
        $f = @(Get-MgEffectiveField -Design $design -ContentTypeName 'Contract')
        $f.Name | Should -Be @('Supplier', 'PurchDepartment', 'ContractNumber', 'ContractValue', 'ExpiryDate')
        ($f | Where-Object Required).Name | Should -Be @('Supplier', 'PurchDepartment', 'ContractNumber', 'ExpiryDate')
    }
}

Describe 'Test-MgFilingPlan' {
    It 'catches a broken expression, an unknown content type, a group that is no field, a bad folder token' {
        $p = $plan | ConvertTo-Json -Depth 10 | ConvertFrom-Json
        $p.rules = @(
            [pscustomobject]@{ name = 'r1'; contentType = 'Contract'; folder = ''; match = '^CTR-(?<ContractNumber' },
            [pscustomobject]@{ name = 'r2'; contentType = 'Memo'; folder = ''; match = '^MEMO' },
            [pscustomobject]@{ name = 'r3'; contentType = 'Invoice'; folder = '{Supplier}'; match = '^INV-(?<PoNumber>\d+)' })
        (Rules (Test-MgFilingPlan -Plan $p -Design $design) | Sort-Object) | Should -Be @('FP001', 'FP002', 'FP003', 'FP004')
    }
}

Describe 'Resolve-MgFilingPlan (nine sample files, today = 2026-12-01)' {
    BeforeAll {
        $script:r = @(Resolve-MgFilingPlan -Plan $plan -Design $design -FileName (Get-ChildItem $samples -File | Sort-Object Name).Name)
    }

    It 'files five, flags one incomplete, one invalid, two unmatched' {
        @($r | Where-Object Status -eq 'Ready') | Should -HaveCount 5
        @($r | Where-Object Status -eq 'Incomplete').FileName | Should -Be 'CTR-2026-0050 Adventure Works.txt'
        @($r | Where-Object Status -eq 'Invalid').FileName | Should -Be 'INV-10023 Northwind Traders 2026-13-01.txt'
        @($r | Where-Object Status -eq 'Unmatched') | Should -HaveCount 2
    }

    It 'reads the metadata from the name and picks the document set' {
        $c = $r | Where-Object FileName -like 'CTR-2026-0043*'
        $c.ContentType | Should -Be 'Contract'
        $c.Folder | Should -Be 'Northwind Traders'
        $c.Values.ContractNumber | Should -Be '2026-0043'
        $c.Values.Supplier | Should -Be 'Northwind Traders'
        $c.Values.ExpiryDate | Should -Be '2028-01-05'
        $c.Missing | Should -HaveCount 0     # Department comes from the library default
    }

    It 'says what is missing' {
        ($r | Where-Object Status -eq 'Incomplete').Missing | Should -Be @('ExpiryDate')
    }
}

Describe 'ConvertTo-MgSiteColumnXml' {
    It 'every site column becomes valid field XML with a fixed ID and clean name' {
        foreach ($c in $design.siteColumns) {
            $x = [xml](ConvertTo-MgSiteColumnXml -Column $c)
            $x.Field.ID | Should -Be "{$($c.id)}"
            $x.Field.Name | Should -Be $c.internalName
            $x.Field.StaticName | Should -Be $c.internalName
        }
    }

    It 'choices, date-only, euro currency and escaping' {
        $choice = [xml](ConvertTo-MgSiteColumnXml -Column ($design.siteColumns | Where-Object internalName -eq 'PurchDepartment'))
        @($choice.Field.CHOICES.CHOICE) | Should -Be @('Purchasing', 'Facilities', 'IT', 'Finance')
        ([xml](ConvertTo-MgSiteColumnXml -Column ($design.siteColumns | Where-Object internalName -eq 'ExpiryDate'))).Field.Format | Should -Be 'DateOnly'
        ([xml](ConvertTo-MgSiteColumnXml -Column ($design.siteColumns | Where-Object internalName -eq 'ContractValue'))).Field.LCID | Should -Be '-2'
        $odd = [pscustomobject]@{ internalName = 'RnD'; displayName = 'R&D <lab>'; type = 'Text'; id = [guid]::Empty }
        ([xml](ConvertTo-MgSiteColumnXml -Column $odd)).Field.DisplayName | Should -Be 'R&D <lab>'
    }
}

Describe 'Test-MgDocumentItem (audit rules)' {
    It 'a healthy contract has no findings' {
        @(Audit @(Item 'ok.txt')) | Should -HaveCount 0
    }

    It 'flags an empty required field' {
        $f = Audit @(Item 'x.txt' -Values @{ ExpiryDate = $null })
        Rules $f | Should -Be @('DA001')
        $f.Message | Should -Match 'ExpiryDate'
    }

    It "flags files that aren't one of the library's content types" {
        Rules (Audit @(Item 'x.txt' -Ct 'Document')) | Should -Be @('DA002')
    }

    It 'stale check-out: 14 days is fine, 15 is not' {
        @(Audit @(Item 'a.txt' -CheckedOutTo 'Alex Demo' -Modified $today.AddDays(-14))) | Should -HaveCount 0
        Rules (Audit @(Item 'b.txt' -CheckedOutTo 'Alex Demo' -Modified $today.AddDays(-15))) | Should -Be @('DA003')
    }

    It 'expiry: 60 days warns, 61 does not, yesterday is an error' {
        Rules (Audit @(Item 'a.txt' -Values @{ ExpiryDate = $today.AddDays(60) })) | Should -Be @('DA004')
        @(Audit @(Item 'b.txt' -Values @{ ExpiryDate = $today.AddDays(61) })) | Should -HaveCount 0
        Rules (Audit @(Item 'c.txt' -Values @{ ExpiryDate = $today.AddDays(-1) })) | Should -Be @('DA005')
    }

    It 'missing document ID on files, not on document sets' {
        Rules (Audit @(Item 'a.txt' -DocId '')) | Should -Be @('DA006')
        @(Audit @(Item 'Fabrikam' -Ct 'Supplier File' -Values @{ Supplier = 'Fabrikam' } -DocId '' -Folder)) | Should -HaveCount 0
    }

    It 'ConvertFrom-MgListItem flattens a list item' {
        $li = [pscustomobject]@{
            ContentType = [pscustomobject]@{ Name = 'Contract' }
            FieldValues = @{ FileLeafRef = 'c.txt'; FileDirRef = '/sites/Purchasing/SupplierDocuments/Fabrikam'; FSObjType = 0
                CheckoutUser = [pscustomobject]@{ LookupValue = 'Alex Demo' }; Modified = $today; _dlc_DocId = 'CONTOSO-1-5' }
        }
        $o = $li | ConvertFrom-MgListItem
        $o.Name | Should -Be 'c.txt'; $o.ContentType | Should -Be 'Contract'; $o.CheckedOutTo | Should -Be 'Alex Demo'
        $o.IsFolder | Should -BeFalse; $o.DocId | Should -Be 'CONTOSO-1-5'
    }
}

Describe 'Tenant functions (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
        $script:writeCmds = 'Enable-PnPFeature', 'Add-PnPFieldFromXml', 'Add-PnPContentType', 'Add-PnPFieldToContentType',
            'Add-PnPContentTypeToDocumentSet', 'Set-PnPDocumentSetField', 'New-PnPList', 'Set-PnPList', 'Add-PnPContentTypeToList',
            'Set-PnPDefaultContentTypeToList', 'Remove-PnPContentTypeFromList', 'Set-PnPDefaultColumnValues'
    }

    It 'provisions features, columns, content types, the document set and the library on an empty site' {
        Mock -ModuleName MgDocMgmt Get-PnPFeature { $null }
        Mock -ModuleName MgDocMgmt Get-PnPField { $null }
        Mock -ModuleName MgDocMgmt Get-PnPContentType { $null }
        Mock -ModuleName MgDocMgmt Get-PnPList { $null }
        foreach ($c in $writeCmds) { Mock -ModuleName MgDocMgmt $c { } }
        $steps = @(Invoke-MgDocMgmtProvisioning -Design $design)
        Should -Invoke -ModuleName MgDocMgmt Enable-PnPFeature -Times 1 -Exactly -ParameterFilter { $Identity -eq [guid]'3BAE86A2-776D-499D-9DB8-FA4CDC7884F8' -and $Scope -eq 'Site' }
        Should -Invoke -ModuleName MgDocMgmt Enable-PnPFeature -Times 1 -Exactly -ParameterFilter { $Identity -eq [guid]'B50E3104-6812-424F-A011-CC90E6327318' }
        Should -Invoke -ModuleName MgDocMgmt Add-PnPFieldFromXml -Times 8 -Exactly
        Should -Invoke -ModuleName MgDocMgmt Add-PnPContentType -Times 4 -Exactly
        Should -Invoke -ModuleName MgDocMgmt Add-PnPContentType -Times 1 -Exactly -ParameterFilter { $Name -eq 'Contract' -and $ContentTypeId -eq '0x010100D5F0B586695B489A84366F90C59E924901' }
        Should -Invoke -ModuleName MgDocMgmt Add-PnPFieldToContentType -Times 9 -Exactly
        Should -Invoke -ModuleName MgDocMgmt Add-PnPFieldToContentType -Times 1 -Exactly -ParameterFilter { $Field.Name -eq 'ExpiryDate' -and "$ContentType" -eq 'Contract' -and $Required }
        Should -Invoke -ModuleName MgDocMgmt Add-PnPContentTypeToDocumentSet -Times 1 -Exactly -ParameterFilter { $DocumentSet.Name -eq 'Supplier File' -and $ContentType.Count -eq 2 }
        Should -Invoke -ModuleName MgDocMgmt Set-PnPDocumentSetField -Times 1 -Exactly -ParameterFilter { $Field.Name -eq 'Supplier' -and $SetSharedField }
        Should -Invoke -ModuleName MgDocMgmt New-PnPList -Times 1 -Exactly -ParameterFilter { $Template -eq 'DocumentLibrary' -and $Url -eq 'SupplierDocuments' -and $EnableContentTypes }
        Should -Invoke -ModuleName MgDocMgmt Set-PnPList -Times 1 -Exactly -ParameterFilter { $ForceCheckout -eq $false }
        Should -Invoke -ModuleName MgDocMgmt Add-PnPContentTypeToList -Times 3 -Exactly
        Should -Invoke -ModuleName MgDocMgmt Add-PnPContentTypeToList -Times 1 -Exactly -ParameterFilter { "$ContentType" -eq 'Contract' -and $DefaultContentType }
        Should -Invoke -ModuleName MgDocMgmt Remove-PnPContentTypeFromList -Times 1 -Exactly -ParameterFilter { "$ContentType" -eq 'Document' }
        Should -Invoke -ModuleName MgDocMgmt Set-PnPDefaultColumnValues -Times 1 -Exactly -ParameterFilter { $Field.Name -eq 'PurchDepartment' -and $Value -contains 'Purchasing' }
        $steps.Count | Should -BeGreaterThan 20
    }

    It 'is idempotent: when everything exists it adds nothing' {
        Mock -ModuleName MgDocMgmt Get-PnPFeature { [pscustomobject]@{ DefinitionId = [guid]::NewGuid() } }
        Mock -ModuleName MgDocMgmt Get-PnPField { [pscustomobject]@{ InternalName = $Identity.Name } }
        Mock -ModuleName MgDocMgmt Get-PnPContentType -ParameterFilter { $List } {
            'Supplier File', 'Contract', 'Invoice' | ForEach-Object { [pscustomobject]@{ Name = $_ } } }
        Mock -ModuleName MgDocMgmt Get-PnPContentType {
            $ct = $script:design.contentTypes | Where-Object id -eq "$Identity"
            [pscustomobject]@{ Name = $ct.name; FieldLinks = @($ct.fields | ForEach-Object { [pscustomobject]@{ Name = $_.name } }) } }
        Mock -ModuleName MgDocMgmt Get-PnPList { [pscustomobject]@{ Title = 'Supplier Documents' } }
        foreach ($c in $writeCmds) { Mock -ModuleName MgDocMgmt $c { } }
        $null = Invoke-MgDocMgmtProvisioning -Design $design
        foreach ($c in 'Enable-PnPFeature', 'Add-PnPFieldFromXml', 'Add-PnPContentType', 'Add-PnPFieldToContentType', 'New-PnPList', 'Add-PnPContentTypeToList', 'Remove-PnPContentTypeFromList') {
            Should -Invoke -ModuleName MgDocMgmt $c -Times 0 -Exactly -Because $c
        }
        Should -Invoke -ModuleName MgDocMgmt Set-PnPDefaultContentTypeToList -Times 1 -Exactly -ParameterFilter { "$ContentType" -eq 'Contract' }
    }

    It '-WhatIf writes nothing' {
        Mock -ModuleName MgDocMgmt Get-PnPFeature { $null }
        Mock -ModuleName MgDocMgmt Get-PnPField { $null }
        Mock -ModuleName MgDocMgmt Get-PnPContentType { $null }
        Mock -ModuleName MgDocMgmt Get-PnPList { $null }
        foreach ($c in $writeCmds) { Mock -ModuleName MgDocMgmt $c { throw 'WhatIf violated' } }
        $steps = @(Invoke-MgDocMgmtProvisioning -Design $design -WhatIf)
        @($steps | Where-Object Action -eq 'AddContentType') | Should -HaveCount 4
    }

    It 'files the ready documents into one document set per supplier, with content type and metadata' {
        Mock -ModuleName MgDocMgmt Get-PnPFolder { if ($AsListItem) { [pscustomobject]@{ Id = 7 } } else { throw 'File Not Found.' } }
        Mock -ModuleName MgDocMgmt Add-PnPDocumentSet { }
        Mock -ModuleName MgDocMgmt Set-PnPListItem { }
        Mock -ModuleName MgDocMgmt Get-PnPFile { $null }
        Mock -ModuleName MgDocMgmt Add-PnPFile { }
        $steps = @(Invoke-MgFiling -Plan $plan -Design $design -Path $samples)
        Should -Invoke -ModuleName MgDocMgmt Add-PnPDocumentSet -Times 3 -Exactly -ParameterFilter { "$ContentType" -eq 'Supplier File' }
        Should -Invoke -ModuleName MgDocMgmt Set-PnPListItem -Times 1 -Exactly -ParameterFilter { $Values.Supplier -eq 'Northwind Traders' }
        Should -Invoke -ModuleName MgDocMgmt Add-PnPFile -Times 5 -Exactly
        Should -Invoke -ModuleName MgDocMgmt Add-PnPFile -Times 1 -Exactly -ParameterFilter {
            $Folder.ServerRelativeUrl -eq 'SupplierDocuments/Fabrikam' -and "$ContentType" -eq 'Invoice' -and $Values.InvoiceNumber -eq '10021' }
        @($steps | Where-Object Action -like 'Skip*') | Should -HaveCount 4
    }

    It '-IncludeIncomplete uploads the incomplete file too (the audit will catch it); existing files are skipped' {
        Mock -ModuleName MgDocMgmt Get-PnPFolder { if ($AsListItem) { [pscustomobject]@{ Id = 7 } } else { [pscustomobject]@{ Name = 'exists' } } }
        Mock -ModuleName MgDocMgmt Add-PnPDocumentSet { throw 'should not create' }
        Mock -ModuleName MgDocMgmt Get-PnPFile { if ($Url -like '*INV-10021*') { [pscustomobject]@{ Name = 'x' } } }
        Mock -ModuleName MgDocMgmt Add-PnPFile { }
        $steps = @(Invoke-MgFiling -Plan $plan -Design $design -Path $samples -IncludeIncomplete)
        Should -Invoke -ModuleName MgDocMgmt Add-PnPFile -Times 5 -Exactly
        ($steps | Where-Object Action -eq 'UploadIncomplete').Target | Should -Be 'CTR-2026-0050 Adventure Works.txt'
        ($steps | Where-Object Action -eq 'SkipExists').Target | Should -BeLike 'INV-10021*'
    }

    It 'audits the live library' {
        Mock -ModuleName MgDocMgmt Get-PnPListItem {
            [pscustomobject]@{ ContentType = [pscustomobject]@{ Name = 'Contract' }
                FieldValues = @{ FileLeafRef = 'CTR-2026-0050 Adventure Works.txt'; FileDirRef = 'SupplierDocuments/Adventure Works'; FSObjType = 0
                    Supplier = 'Adventure Works'; PurchDepartment = 'Purchasing'; ContractNumber = '2026-0050'; ExpiryDate = $null
                    Modified = [datetime]'2026-12-01'; _dlc_DocId = 'CONTOSO-1-9' } }
            [pscustomobject]@{ ContentType = [pscustomobject]@{ Name = 'Document' }
                FieldValues = @{ FileLeafRef = 'scan_0001.txt'; FileDirRef = 'SupplierDocuments'; FSObjType = 0; Modified = [datetime]'2026-12-01'; _dlc_DocId = 'CONTOSO-1-10' } }
        }
        $f = @(Get-MgLibraryAudit -Design $design -Library 'Supplier Documents' -Today $today)
        (Rules $f | Sort-Object) | Should -Be @('DA001', 'DA002')
        Should -Invoke -ModuleName MgDocMgmt Get-PnPListItem -Times 1 -Exactly -ParameterFilter { $IncludeContentType -and $PageSize -eq 500 }
    }
}
