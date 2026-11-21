BeforeAll {
    $script:Root = Resolve-Path (Join-Path $PSScriptRoot '../..')
    $script:Script = Join-Path $script:Root 'src/scripts/Provision-ContosoInspections.ps1'
    $script:Schema = Get-Content (Join-Path $script:Root 'src/schema/contosoinspections.schema.json') -Raw | ConvertFrom-Json
    $script:Canonical = Join-Path $script:Root '../12-build-a-model-driven-app-from-start-to-end/src/schema/contosoinspections.schema.json'
    $script:Env = 'https://contoso-dev.crm4.dynamics.com'
}

Describe 'Provision-ContosoInspections.ps1' {
    It 'parses without errors' {
        $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($script:Script, [ref]$null, [ref]$errors)
        $errors | Should -BeNullOrEmpty
    }

    It 'reads the same schema file as episode 12 (an exact copy)' {
        (Get-FileHash (Join-Path $script:Root 'src/schema/contosoinspections.schema.json')).Hash |
            Should -Be (Get-FileHash $script:Canonical).Hash
    }

    It '-PlanOnly prints the plan and never calls the service' {
        Mock Invoke-RestMethod { throw 'must not be called' }
        $out = & $script:Script -EnvironmentUrl $script:Env -PlanOnly 6>&1 | Out-String
        $out | Should -Match 'nothing is sent'
        $out | Should -Match 'cin_inspectionitem'
        $out | Should -Match 'cin_inspection_inspectionitem'
        $out | Should -Match 'cin_site_sitecode'
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
            $body.customizationoptionvalueprefix | Should -Be 45532
        }

        It 'puts every metadata create in the solution through the header' {
            $meta = @($global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match '/(EntityDefinitions|RelationshipDefinitions)' })
            # 4 tables + 21 columns (the 3 lookups come with their relationships) + 3 relationships + 1 alternate key
            $meta.Count | Should -Be (4 + 21 + 3 + 1)
            foreach ($m in $meta) { $m.Headers.'MSCRM.SolutionUniqueName' | Should -Be 'ContosoInspections' }
        }

        It 'numbers choice options from the option value prefix, using the values the schema gives' {
            $call = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match 'Attributes$' -and $_.Body -match '"SchemaName":"cin_risklevel"' }
            $body = $call.Body | ConvertFrom-Json
            $values = @($body.OptionSet.Options | ForEach-Object Value)
            $values | Should -Be @(455320000, 455320001, 455320002)
            $body.DefaultFormValue | Should -Be 455320001
            $status = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match 'Attributes$' -and $_.Body -match '"SchemaName":"cin_status"' }
            @(($status.Body | ConvertFrom-Json).OptionSet.Options | ForEach-Object { $_.Label.LocalizedLabels[0].Label }) |
                Should -Be @('Draft', 'In progress', 'Submitted', 'Approved', 'Rejected')
        }

        It 'makes the item a child of the inspection (parental cascade); the site restricts deletes and the inspector removes the link' {
            $rels = @($global:ProvCalls | Where-Object { $_.Uri -match '/RelationshipDefinitions$' } | ForEach-Object { $_.Body | ConvertFrom-Json })
            $child = $rels | Where-Object SchemaName -eq 'cin_inspection_inspectionitem'
            $child.CascadeConfiguration.Delete | Should -Be 'Cascade'
            $child.CascadeConfiguration.Reparent | Should -Be 'Cascade'
            $child.Lookup.SchemaName | Should -Be 'cin_inspectionid'
            $child.Lookup.RequiredLevel.Value | Should -Be 'ApplicationRequired'
            ($rels | Where-Object SchemaName -eq 'cin_site_inspection').CascadeConfiguration.Delete | Should -Be 'Restrict'
            ($rels | Where-Object SchemaName -eq 'cin_inspector_inspection').CascadeConfiguration.Delete | Should -Be 'RemoveLink'
            ($rels | Where-Object SchemaName -eq 'cin_inspector_inspection').Lookup.RequiredLevel.Value | Should -Be 'None'
        }

        It 'creates the image column with an explicit size limit' {
            $call = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match 'Attributes$' -and $_.Body -match '"SchemaName":"cin_photo"' }
            ($call.Body | ConvertFrom-Json).MaxSizeInKB | Should -Be 10240
        }

        It 'creates the auto number, the whole number, the secured column, the typed strings and quick create exactly as the schema says' {
            $bodies = @($global:ProvCalls | Where-Object { $_.Method -eq 'POST' } | ForEach-Object { $_.Body } | Where-Object { $_ })
            $inspection = $bodies | Where-Object { $_ -match 'EntityMetadata' -and $_ -match '"SchemaName":"cin_inspection"' } | ConvertFrom-Json
            $inspection.Attributes[0].AutoNumberFormat | Should -Be 'INS-{SEQNUM:5}'
            $inspection.IsQuickCreateEnabled | Should -BeTrue
            $inspection.IsAvailableOffline | Should -BeTrue
            $inspection.OwnershipType | Should -Be 'UserOwned'
            $score = $bodies | Where-Object { $_ -match '"SchemaName":"cin_score"' } | ConvertFrom-Json
            $score.MinValue | Should -Be 0
            $score.MaxValue | Should -Be 100
            ($bodies | Where-Object { $_ -match '"SchemaName":"cin_reviewernotes"' } | ConvertFrom-Json).IsSecured | Should -BeTrue
            ($bodies | Where-Object { $_ -match '"SchemaName":"cin_email"' } | ConvertFrom-Json).FormatName.Value | Should -Be 'Email'
            ($bodies | Where-Object { $_ -match '"SchemaName":"cin_phone"' } | ConvertFrom-Json).FormatName.Value | Should -Be 'Phone'
        }

        It 'creates the alternate key on the site code' {
            $call = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match "cin_site'\)/Keys$" }
            $call | Should -Not -BeNullOrEmpty
            $key = $call.Body | ConvertFrom-Json
            $key.SchemaName | Should -Be 'cin_site_sitecode'
            @($key.KeyAttributes) | Should -Be @('cin_sitecode')
        }

        It 'creates only the field inspector role, with the schema privileges plus the offline ones' {
            $roles = @($global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match '/roles$' } | ForEach-Object { $_.Body | ConvertFrom-Json })
            $roles.Count | Should -Be 1
            $roles[0].name | Should -Be 'Inspection Field Inspector'
            $add = $global:ProvCalls | Where-Object { $_.Uri -match 'AddPrivilegesRole$' }
            $priv = ($add.Body | ConvertFrom-Json).Privileges
            @($priv).Count | Should -Be 17   # 5 + 5 (own records) + 2 + 2 (read sites and inspectors) + 3 offline system tables
            @($priv | Where-Object Depth -eq 'Basic').Count | Should -Be 10
        }

        It 'adds the role privileges and the role to the solution, then publishes' {
            $uris = @($global:ProvCalls | Where-Object Method -eq 'POST' | ForEach-Object { $_.Uri })
            ($uris | Where-Object { $_ -match 'AddPrivilegesRole$' }).Count | Should -Be 1
            ($uris | Where-Object { $_ -match '/AddSolutionComponent$' }).Count | Should -Be 1
            @($uris | Where-Object { $_ -match 'PublishAllXml$' }).Count | Should -Be 1
        }

        It 'seeds sample rows with the supplied inspector email, and the sites with the schema option values' {
            $insp = $global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match '/cin_inspectors$' }
            @($insp).Count | Should -Be 2
            ($insp[0].Body | ConvertFrom-Json).cin_email | Should -Be 'alex.demo@contoso.com'
            $sites = @($global:ProvCalls | Where-Object { $_.Method -eq 'POST' -and $_.Uri -match '/cin_sites$' } | ForEach-Object { $_.Body | ConvertFrom-Json })
            $sites.Count | Should -Be 3
            ($sites | Where-Object cin_sitecode -eq 'HW-01').cin_risklevel | Should -Be 455320002   # High
            ($sites | Where-Object cin_sitecode -eq 'ND-03').cin_risklevel | Should -Be 455320001   # Medium
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
