BeforeAll {
    $script:Root = Resolve-Path (Join-Path $PSScriptRoot '../..')
    $script:Script = Join-Path $script:Root 'src/scripts/Provision-ContosoInspections.ps1'
    $script:Schema = Get-Content (Join-Path $script:Root 'src/schema/contosoinspections.schema.json') -Raw | ConvertFrom-Json
    $script:Env = 'https://contoso-dev.crm4.dynamics.com'
}

Describe 'Provision-ContosoInspections.ps1' {
    It 'parses without errors' {
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($script:Script, [ref]$null, [ref]$errors)
        $errors | Should -BeNullOrEmpty
    }

    It '-PlanOnly prints the plan and never calls the service' {
        Mock Invoke-RestMethod { throw 'must not be called' }
        $out = & $script:Script -EnvironmentUrl $script:Env -PlanOnly 6>&1 | Out-String
        $out | Should -Match 'nothing is sent'
        $out | Should -Match 'cin_finding'
        $out | Should -Match 'cin_inspection_finding'
        Should -Invoke Invoke-RestMethod -Times 0 -Exactly
    }

    It 'refuses to run without a token (it never signs in)' {
        Mock Invoke-RestMethod { throw 'must not be called' }
        { & $script:Script -EnvironmentUrl $script:Env -AccessToken '' } | Should -Throw '*No access token*'
        Should -Invoke Invoke-RestMethod -Times 0 -Exactly
    }
}

Describe 'Provisioning against a mocked Dataverse' {
    BeforeAll {
        $global:ProvCalls = [System.Collections.Generic.List[object]]::new()
    }
    BeforeEach { $global:ProvCalls.Clear() }

    Context 'empty environment' {
        BeforeEach {
            Mock Invoke-RestMethod {
                $global:ProvCalls.Add([pscustomobject]@{ Method = $Method; Uri = [string]$Uri; Headers = $Headers; Body = $Body })
                $id = '00000000-0000-0000-0000-000000000001'
                if ($Method -eq 'POST') { return [pscustomobject]@{ publisherid = $id; solutionid = $id; roleid = $id; cin_siteid = $id; cin_inspectorid = $id } }
                if ($Uri -match 'businessunits') { return [pscustomobject]@{ value = @([pscustomobject]@{ businessunitid = $id }) } }
                if ($Uri -match '/privileges') { return [pscustomobject]@{ value = @([pscustomobject]@{ privilegeid = $id; name = 'x' }) } }
                if ($Uri -match 'filter') { return [pscustomobject]@{ value = @() } }
                return $null   # metadata existence probes: not found
            }
            $null = & $script:Script -EnvironmentUrl $script:Env -AccessToken 'zero-token' -SeedData -AlexEmail 'alex.demo@contoso.com' 6>&1
        }

        It 'sends the bearer token and OData headers on every call' {
            $global:ProvCalls.Count | Should -BeGreaterThan 20
            foreach ($c in $global:ProvCalls) {
                $c.Headers.Authorization | Should -Be 'Bearer zero-token'
                $c.Headers.'OData-Version' | Should -Be '4.0'
            }
        }

        It 'only talks to the given environment, under /api/data/v9.2' {
            foreach ($c in $global:ProvCalls) { $c.Uri | Should -Match '^https://contoso-dev\.crm4\.dynamics\.com/api/data/v9\.2/' }
        }

        It 'creates the publisher before the solution and the solution before any table' {
            $posts = @($global:ProvCalls | Where-Object Method -eq 'POST' | ForEach-Object { $_.Uri })
            $pub = [array]::FindIndex($posts, [Predicate[string]] { param($u) $u -match '/publishers$' })
            $sol = [array]::FindIndex($posts, [Predicate[string]] { param($u) $u -match '/solutions$' })
            $tab = [array]::FindIndex($posts, [Predicate[string]] { param($u) $u -match '/EntityDefinitions$' })
            $pub | Should -BeGreaterOrEqual 0
            $pub | Should -BeLessThan $sol
            $sol | Should -BeLessThan $tab
        }

        It 'uses the publisher prefix and option value prefix from the schema' {
            $pubCall = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match '/publishers$' }
            $body = $pubCall.Body | ConvertFrom-Json
            $body.customizationprefix | Should -Be 'cin'
            $body.customizationoptionvalueprefix | Should -Be 72700
        }

        It 'puts every metadata create in the solution through the header' {
            $meta = @($global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match '/(EntityDefinitions|RelationshipDefinitions)' })
            $meta.Count | Should -Be (4 + 17 + 3)
            foreach ($m in $meta) { $m.Headers.'MSCRM.SolutionUniqueName' | Should -Be 'ContosoInspections' }
        }

        It 'numbers choice options from the option value prefix' {
            $call = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Body -match 'cin_RiskRating' }
            $body = $call.Body | ConvertFrom-Json
            $values = @($body.OptionSet.Options | ForEach-Object Value)
            $values[0] | Should -Be 727000000
            $values | Should -Be @(727000000, 727000001, 727000002)
        }

        It 'makes the finding a child of the inspection (parental cascade) and the lookups restrict deletes' {
            $rels = @($global:ProvCalls | Where-Object { $_.Uri -match '/RelationshipDefinitions$' } | ForEach-Object { $_.Body | ConvertFrom-Json })
            ($rels | Where-Object SchemaName -eq 'cin_inspection_finding').CascadeConfiguration.Delete | Should -Be 'Cascade'
            ($rels | Where-Object SchemaName -eq 'cin_site_inspection').CascadeConfiguration.Delete | Should -Be 'Restrict'
        }

        It 'creates the image column with an explicit size limit' {
            $call = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Body -match 'cin_Photo' }
            ($call.Body | ConvertFrom-Json).MaxSizeInKB | Should -BeGreaterThan 0
        }

        It 'adds the role privileges and the role to the solution, then publishes' {
            $uris = @($global:ProvCalls | Where-Object Method -eq 'POST' | ForEach-Object { $_.Uri })
            ($uris | Where-Object { $_ -match 'AddPrivilegesRole$' }).Count | Should -Be 1
            ($uris | Where-Object { $_ -match '/AddSolutionComponent$' }).Count | Should -Be 1
            @($uris | Where-Object { $_ -match 'PublishAllXml$' }).Count | Should -Be 1
        }

        It 'seeds sample rows with the supplied inspector email' {
            $insp = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match '/cin_inspectors$' }
            @($insp).Count | Should -Be 2
            ($insp[0].Body | ConvertFrom-Json).cin_workemail | Should -Be 'alex.demo@contoso.com'
        }
    }

    Context 'everything already exists (idempotent)' {
        BeforeEach {
            Mock Invoke-RestMethod {
                $global:ProvCalls.Add([pscustomobject]@{ Method = $Method; Uri = [string]$Uri; Headers = $Headers; Body = $Body })
                $id = '00000000-0000-0000-0000-000000000001'
                if ($Method -eq 'POST') { return [pscustomobject]@{} }
                if ($Uri -match 'businessunits') { return [pscustomobject]@{ value = @([pscustomobject]@{ businessunitid = $id }) } }
                if ($Uri -match '/privileges') { return [pscustomobject]@{ value = @([pscustomobject]@{ privilegeid = $id }) } }
                if ($Uri -match 'filter') { return [pscustomobject]@{ value = @([pscustomobject]@{ publisherid = $id; solutionid = $id; roleid = $id }) } }
                return [pscustomobject]@{ MetadataId = $id }
            }
            $null = & $script:Script -EnvironmentUrl $script:Env -AccessToken 'zero-token' -SkipSecurityRole 6>&1
        }

        It 'creates no table, column, relationship, publisher or solution' {
            $posts = @($global:ProvCalls | Where-Object Method -eq 'POST' | ForEach-Object { $_.Uri })
            @($posts | Where-Object { $_ -match 'Definitions|publishers|solutions' }).Count | Should -Be 0
        }

        It 'skips the security role when asked' {
            @($global:ProvCalls | Where-Object { $_.Uri -match '/roles|AddPrivilegesRole' }).Count | Should -Be 0
        }
    }
}
