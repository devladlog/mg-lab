#Requires -Modules @{ ModuleName = 'Pester'; ModuleVersion = '5.5.0' }
# Invoke-Pester ./tests -Output Detailed
# Mocks the real PnP.PowerShell cmdlets (Pester copies their parameter metadata); skipped without PnP.PowerShell.

BeforeDiscovery {
    $script:hasPnP = [bool](Get-Module -ListAvailable PnP.PowerShell)
}

BeforeAll {
    $script:src = Join-Path $PSScriptRoot '..' 'src'
    $script:apply = Join-Path $src 'Set-ListFormatting.ps1'
    $script:map = Join-Path $src 'formats' 'map.json'
}

Describe 'Set-ListFormatting.ps1' {
    It 'parses without errors' {
        $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($apply, [ref]$null, [ref]$errors) | Out-Null
        $errors | Should -HaveCount 0
    }
}

Describe 'Set-ListFormatting.ps1 (PnP cmdlets mocked)' -Skip:(-not $hasPnP) {
    BeforeAll {
        Import-Module PnP.PowerShell -ErrorAction Stop
    }

    It 'lints, then applies four column formats and one view format as compact JSON' {
        Mock Set-PnPField { }
        Mock Set-PnPView { }
        $log = @(& $apply -MapPath $map -NoConnect -Confirm:$false 6>$null)

        Should -Invoke Set-PnPField -Times 4 -Exactly -ParameterFilter { "$List" -eq 'Purchase Requests' }
        Should -Invoke Set-PnPView -Times 1 -Exactly -ParameterFilter { $Identity.Title -eq 'Open requests' }
        Should -Invoke Set-PnPField -Times 1 -Exactly -ParameterFilter {
            $Identity.Name -eq 'DueDate' -and
            ($Values.CustomFormatter | ConvertFrom-Json).style.color -like '=if(@currentField ==*' -and
            $Values.CustomFormatter -notmatch "`n"
        }
        ($log.Action | Sort-Object) -join ',' | Should -Be 'Column,Column,Column,Column,View'
    }

    It 'applies nothing when formatlint finds errors' {
        Mock Set-PnPField { }
        Mock Set-PnPView { }
        { & $apply -MapPath (Join-Path $src 'formats' 'bad' 'map.json') -NoConnect -Confirm:$false 6>$null } |
            Should -Throw '*formatlint found errors*'
        Should -Invoke Set-PnPField -Times 0
        Should -Invoke Set-PnPView -Times 0
    }

    It '-WhatIf changes nothing' {
        Mock Set-PnPField { throw 'WhatIf violated' }
        Mock Set-PnPView { throw 'WhatIf violated' }
        $log = @(& $apply -MapPath $map -NoConnect -SkipLint -WhatIf)
        $log | Should -HaveCount 5
    }

    It '-Reset clears every formatted column and every view in the map' {
        Mock Set-PnPField { }
        Mock Set-PnPView { }
        & $apply -MapPath $map -NoConnect -Reset -Confirm:$false | Out-Null
        Should -Invoke Set-PnPField -Times 4 -Exactly -ParameterFilter { $Values.CustomFormatter -eq '' }
        Should -Invoke Set-PnPView -Times 3 -Exactly -ParameterFilter { $Values.CustomFormatter -eq '' }
    }

    It '-Export saves what is live, pretty-printed' {
        Mock Get-PnPField { [pscustomobject]@{ InternalName = $Identity.Name; CustomFormatter = '{"elmType":"div","txtContent":"@currentField"}' } }
        Mock Get-PnPView { [pscustomobject]@{ Title = $Identity.Title; CustomFormatter = '' } }
        $out = Join-Path $TestDrive 'backup'
        $log = @(& $apply -MapPath $map -NoConnect -Export $out)
        $log | Should -HaveCount 7
        (Get-Content (Join-Path $out 'DueDate.column.json') -Raw | ConvertFrom-Json).txtContent | Should -Be '@currentField'
        Test-Path (Join-Path $out 'open-requests.view.json') | Should -BeTrue
        Should -Invoke Get-PnPView -ParameterFilter { $Includes -contains 'CustomFormatter' }
    }
}
