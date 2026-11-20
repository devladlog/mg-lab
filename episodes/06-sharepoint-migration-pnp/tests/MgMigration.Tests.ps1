BeforeAll { Import-Module "$PSScriptRoot/../src/MgMigration.psm1" -Force }

Describe 'Department mapping' {
    It 'maps legacy folders to SharePoint departments' -ForEach @(
        @{ Path = 'Accounts/2024/Budget.xlsx'; Expected = 'Finance' }
        @{ Path = 'People/Onboarding.docx';    Expected = 'HR' }
        @{ Path = 'Sales & Marketing/Deck.pptx'; Expected = 'Sales' }
    ) { Get-MgDepartment $Path | Should -Be $Expected }

    It 'returns null for unknown folders' { Get-MgDepartment 'Old Stuff/file.txt' | Should -BeNullOrEmpty }
}

Describe 'Document type' {
    It 'classifies by extension' -ForEach @(
        @{ Name = 'a.XLSX'; Expected = 'Spreadsheet' }, @{ Name = 'b.pdf'; Expected = 'Document' },
        @{ Name = 'c.pptx'; Expected = 'Presentation' }, @{ Name = 'd.zip'; Expected = 'Other' }
    ) { Get-MgDocType $Name | Should -Be $Expected }
}

Describe 'Pre-flight checks' {
    BeforeAll { $lib = '/sites/MGLabDemo/Migrated Documents' }

    It 'accepts a normal file' {
        Test-MgMigrationItem -RelativePath 'Accounts/Budget 2025.xlsx' -SizeBytes 2048 -TargetLibraryUrl $lib | Should -BeNullOrEmpty
    }
    It 'flags <Expected>' -ForEach @(
        @{ Path = 'Accounts/~$Budget.xlsx';        Size = 165; Expected = 'BlockedFile' }
        @{ Path = 'Ops/Thumbs.db';                 Size = 10;  Expected = 'BlockedFile' }
        @{ Path = 'People/Contract: v2.docx';      Size = 10;  Expected = 'InvalidCharacters' }
        @{ Path = 'People/Notes .txt';             Size = 10;  Expected = $null }
        @{ Path = 'IT Support/empty.txt';          Size = 0;   Expected = 'EmptyFile' }
        @{ Path = 'Archive/old.docx';              Size = 10;  Expected = 'UnmappedFolder' }
    ) {
        $issues = Test-MgMigrationItem -RelativePath $Path -SizeBytes $Size -TargetLibraryUrl $lib
        if ($Expected) { $issues | Should -Contain $Expected } else { $issues | Should -BeNullOrEmpty }
    }
    It 'flags paths over 400 characters' {
        $name = ('x' * 380) + '.docx'
        Test-MgMigrationItem -RelativePath "Ops/$name" -SizeBytes 10 -TargetLibraryUrl $lib | Should -Contain 'PathTooLong'
    }
    It 'flags trailing spaces in the name' {
        Test-MgMigrationItem -RelativePath 'Ops/Report.docx ' -SizeBytes 10 -TargetLibraryUrl $lib | Should -Contain 'LeadingOrTrailingSpaceOrDot'
    }
}
