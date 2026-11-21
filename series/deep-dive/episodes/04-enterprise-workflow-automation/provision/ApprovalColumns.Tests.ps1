BeforeAll {
    # Stubs so the module's PnP calls can be mocked without PnP.PowerShell installed.
    if (-not (Get-Command Get-PnPList -ErrorAction SilentlyContinue)) {
        function global:Get-PnPList { [CmdletBinding()] param($Identity) }
        function global:Get-PnPField { [CmdletBinding()] param($List, $Identity) }
        function global:Add-PnPFieldFromXml { [CmdletBinding()] param($List, $FieldXml) }
    }
    Import-Module (Join-Path $PSScriptRoot 'ApprovalColumns.psm1') -Force
    $script:ContractPath = Join-Path $PSScriptRoot '..' 'contract' 'approval-columns.json'
}

Describe 'Contract' {
    It 'reads the shared contract with five columns' {
        $c = Read-ApprovalContract -Path $script:ContractPath
        $c.library | Should -Be 'Invoices Inbox'
        $c.columns.Count | Should -Be 5
    }
    It 'refuses duplicate internal names' {
        $tmp = New-TemporaryFile
        '{"library":"X","columns":[{"internalName":"A","type":"Text"},{"internalName":"A","type":"Text"}]}' | Set-Content $tmp
        { Read-ApprovalContract -Path $tmp } | Should -Throw '*Duplicate*'
        Remove-Item $tmp
    }
}

Describe 'ConvertTo-ApprovalFieldXml' {
    It 'builds a choice column with its default and every choice' {
        $c = Read-ApprovalContract -Path $script:ContractPath
        $xml = [xml](ConvertTo-ApprovalFieldXml -Column ($c.columns | Where-Object internalName -eq 'InvApprovalStatus'))
        $xml.Field.Type | Should -Be 'Choice'
        $xml.Field.Default | Should -Be 'Not started'
        $xml.Field.CHOICES.CHOICE | Should -Be @('Not started', 'Waiting for approval', 'Approved', 'Rejected', 'Expired')
    }
    It 'escapes XML in display names' {
        $xml = [xml](ConvertTo-ApprovalFieldXml -Column ([pscustomobject]@{ internalName = 'X'; displayName = 'A & B <c>'; type = 'Text' }))
        $xml.Field.DisplayName | Should -Be 'A & B <c>'
    }
    It 'rejects unknown types' {
        { ConvertTo-ApprovalFieldXml -Column ([pscustomobject]@{ internalName = 'X'; displayName = 'X'; type = 'Lookup' }) } |
            Should -Throw '*Unsupported*'
    }
}

Describe 'Install-ApprovalColumns' {
    BeforeEach { $script:Contract = Read-ApprovalContract -Path $script:ContractPath }

    It 'fails clearly when the episode 1 library is missing' {
        Mock -ModuleName ApprovalColumns Get-PnPList { $null }
        { Install-ApprovalColumns -Contract $script:Contract } | Should -Throw '*episode 1*'
    }
    It 'adds only the missing columns' {
        Mock -ModuleName ApprovalColumns Get-PnPList { [pscustomobject]@{ Title = 'Invoices Inbox' } }
        Mock -ModuleName ApprovalColumns Get-PnPField { if ($Identity -eq 'InvApprovalStatus') { [pscustomobject]@{} } }
        Mock -ModuleName ApprovalColumns Add-PnPFieldFromXml { }
        $result = Install-ApprovalColumns -Contract $script:Contract
        ($result | Where-Object Result -eq 'Exists').Column | Should -Be 'InvApprovalStatus'
        ($result | Where-Object Result -eq 'Added').Count | Should -Be 4
        Should -Invoke -ModuleName ApprovalColumns Add-PnPFieldFromXml -Times 4 -Exactly
    }
    It 'is idempotent: second run adds nothing' {
        Mock -ModuleName ApprovalColumns Get-PnPList { [pscustomobject]@{ Title = 'Invoices Inbox' } }
        Mock -ModuleName ApprovalColumns Get-PnPField { [pscustomobject]@{} }
        Mock -ModuleName ApprovalColumns Add-PnPFieldFromXml { }
        (Install-ApprovalColumns -Contract $script:Contract).Result | Should -Be (@('Exists') * 5)
        Should -Invoke -ModuleName ApprovalColumns Add-PnPFieldFromXml -Times 0 -Exactly
    }
    It 'changes nothing with -WhatIf' {
        Mock -ModuleName ApprovalColumns Get-PnPList { [pscustomobject]@{ Title = 'Invoices Inbox' } }
        Mock -ModuleName ApprovalColumns Get-PnPField { $null }
        Mock -ModuleName ApprovalColumns Add-PnPFieldFromXml { }
        Install-ApprovalColumns -Contract $script:Contract -WhatIf | Out-Null
        Should -Invoke -ModuleName ApprovalColumns Add-PnPFieldFromXml -Times 0 -Exactly
    }
}
