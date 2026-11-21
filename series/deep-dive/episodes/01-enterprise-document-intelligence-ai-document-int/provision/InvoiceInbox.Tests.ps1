# Pester 5+/6 tests. PnP cmdlets are stubbed and mocked: no tenant needed.
BeforeAll {
    # Stubs with the same parameter names as PnP.PowerShell, so Mock has something to replace
    # (PnP.PowerShell isn't installed in CI) and -ParameterFilter can see the arguments.
    function global:Get-PnPList { [CmdletBinding()] param($Identity) }
    function global:New-PnPList { [CmdletBinding()] param($Title, $Template, [switch] $OnQuickLaunch) }
    function global:Set-PnPList { [CmdletBinding()] param($Identity, $EnableVersioning) }
    function global:Get-PnPField { [CmdletBinding()] param($List, $Identity) }
    function global:Add-PnPFieldFromXml { [CmdletBinding()] param($List, $FieldXml) }
    Import-Module (Join-Path $PSScriptRoot 'InvoiceInbox.psm1') -Force
    $script:ContractPath = Join-Path $PSScriptRoot '..' 'src' 'docintel' 'columns.json'
    $script:Contract = Read-InvoiceContract -Path $script:ContractPath
}

Describe 'Read-InvoiceContract' {
    It 'reads the shared contract' {
        $script:Contract.library | Should -Be 'Invoices Inbox'
        $script:Contract.columns.Count | Should -Be 13
    }
    It 'rejects duplicate internal names' {
        $tmp = Join-Path ([IO.Path]::GetTempPath()) "contract-$([guid]::NewGuid()).json"
        '{"library":"X","columns":[{"internalName":"A"},{"internalName":"A"}]}' | Set-Content $tmp
        { Read-InvoiceContract -Path $tmp } | Should -Throw '*Duplicate*A*'
        Remove-Item $tmp
    }
}

Describe 'ConvertTo-FieldXml' {
    It 'produces well-formed XML for every contract column' {
        foreach ($col in $script:Contract.columns) {
            $xml = [xml](ConvertTo-FieldXml -Column $col)
            $xml.Field.Name | Should -Be $col.internalName
            $xml.Field.StaticName | Should -Be $col.internalName
            $xml.Field.DisplayName | Should -Be $col.displayName
        }
    }
    It 'makes dates date-only' {
        $col = $script:Contract.columns | Where-Object internalName -eq 'InvDate'
        ([xml](ConvertTo-FieldXml -Column $col)).Field.Format | Should -Be 'DateOnly'
    }
    It 'writes choices and the default for the status column' {
        $col = $script:Contract.columns | Where-Object internalName -eq 'InvStatus'
        $f = ([xml](ConvertTo-FieldXml -Column $col)).Field
        $f.Type | Should -Be 'Choice'
        $f.Default | Should -Be 'Pending'
        @($f.CHOICES.CHOICE) | Should -Be @('Pending', 'Ready', 'Needs review', 'Rejected')
    }
    It 'indexes the duplicate key (it is used in a filter)' {
        $col = $script:Contract.columns | Where-Object internalName -eq 'InvDedupKey'
        ([xml](ConvertTo-FieldXml -Column $col)).Field.Indexed | Should -Be 'TRUE'
    }
    It 'escapes XML characters in display names' {
        $col = [pscustomobject]@{ internalName = 'InvX'; displayName = 'Tax & <fees>'; type = 'Text' }
        ([xml](ConvertTo-FieldXml -Column $col)).Field.DisplayName | Should -Be 'Tax & <fees>'
    }
    It 'refuses unknown types' {
        { ConvertTo-FieldXml -Column ([pscustomobject]@{ internalName = 'X'; displayName = 'X'; type = 'Lookup' }) } |
            Should -Throw '*Unsupported*'
    }
}

Describe 'Install-InvoiceInbox' {
    It 'creates the library and adds all columns on an empty site' {
        Mock -ModuleName InvoiceInbox Get-PnPList { $null }
        Mock -ModuleName InvoiceInbox New-PnPList { [pscustomobject]@{ Title = 'Invoices Inbox' } }
        Mock -ModuleName InvoiceInbox Set-PnPList { }
        Mock -ModuleName InvoiceInbox Get-PnPField { $null }
        Mock -ModuleName InvoiceInbox Add-PnPFieldFromXml { }

        $result = Install-InvoiceInbox -Contract $script:Contract

        Should -Invoke -ModuleName InvoiceInbox New-PnPList -Times 1 -Exactly -ParameterFilter {
            $Title -eq 'Invoices Inbox' -and $Template -eq 'DocumentLibrary' }
        Should -Invoke -ModuleName InvoiceInbox Set-PnPList -Times 1 -Exactly -ParameterFilter { $EnableVersioning -eq $true }
        Should -Invoke -ModuleName InvoiceInbox Add-PnPFieldFromXml -Times 13 -Exactly
        ($result | Where-Object Result -eq 'Added').Count | Should -Be 13
    }

    It 'is idempotent: a second run adds nothing' {
        Mock -ModuleName InvoiceInbox Get-PnPList { [pscustomobject]@{ Title = 'Invoices Inbox' } }
        Mock -ModuleName InvoiceInbox New-PnPList { }
        Mock -ModuleName InvoiceInbox Set-PnPList { }
        Mock -ModuleName InvoiceInbox Get-PnPField { [pscustomobject]@{ InternalName = $Identity } }
        Mock -ModuleName InvoiceInbox Add-PnPFieldFromXml { }

        $result = Install-InvoiceInbox -Contract $script:Contract

        Should -Invoke -ModuleName InvoiceInbox New-PnPList -Times 0 -Exactly
        Should -Invoke -ModuleName InvoiceInbox Add-PnPFieldFromXml -Times 0 -Exactly
        ($result | Where-Object Result -eq 'Exists').Count | Should -Be 13
    }

    It 'adds only the missing column' {
        Mock -ModuleName InvoiceInbox Get-PnPList { [pscustomobject]@{ Title = 'Invoices Inbox' } }
        Mock -ModuleName InvoiceInbox Set-PnPList { }
        Mock -ModuleName InvoiceInbox Get-PnPField { if ($Identity -ne 'InvDedupKey') { [pscustomobject]@{ InternalName = $Identity } } }
        Mock -ModuleName InvoiceInbox Add-PnPFieldFromXml { }

        $result = Install-InvoiceInbox -Contract $script:Contract

        Should -Invoke -ModuleName InvoiceInbox Add-PnPFieldFromXml -Times 1 -Exactly -ParameterFilter { $FieldXml -match 'Name="InvDedupKey"' }
        ($result | Where-Object Result -eq 'Added').Column | Should -Be 'InvDedupKey'
    }

    It 'changes nothing with -WhatIf' {
        Mock -ModuleName InvoiceInbox Get-PnPList { $null }
        Mock -ModuleName InvoiceInbox New-PnPList { }
        Mock -ModuleName InvoiceInbox Set-PnPList { }
        Mock -ModuleName InvoiceInbox Get-PnPField { $null }
        Mock -ModuleName InvoiceInbox Add-PnPFieldFromXml { }

        Install-InvoiceInbox -Contract $script:Contract -WhatIf | Out-Null

        Should -Invoke -ModuleName InvoiceInbox New-PnPList -Times 0 -Exactly
        Should -Invoke -ModuleName InvoiceInbox Set-PnPList -Times 0 -Exactly
        Should -Invoke -ModuleName InvoiceInbox Add-PnPFieldFromXml -Times 0 -Exactly
    }
}

Describe 'New-InvoiceInbox.ps1' {
    It 'parses without errors' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $PSScriptRoot 'New-InvoiceInbox.ps1'), [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -BeNullOrEmpty
    }
}
