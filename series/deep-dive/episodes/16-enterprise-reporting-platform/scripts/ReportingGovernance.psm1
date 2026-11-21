#Requires -Version 7.0
Set-StrictMode -Version Latest

# Governance as code for the Contoso reporting platform.
# Everything here is pure (builds requests, evaluates a policy against scanner output) except Invoke-RlsCheck,
# which calls the Power BI REST API and therefore needs a tenant, a token and the right permissions.

$script:DeployItemTypes = @('Report', 'SemanticModel', 'Dashboard', 'PaginatedReport', 'Datamart', 'Lakehouse', 'Warehouse', 'Notebook', 'DataPipeline', 'Dataflow', 'VariableLibrary')

function Read-JsonFile {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "File not found: $Path" }
    Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json -Depth 32
}

function Get-OptionalProperty {
    param($Object, [string]$Name)
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name) { return $Object.$Name }
    return $null
}

function New-ScanRequest {
    <#
    .SYNOPSIS Splits workspace ids into getInfo requests. The API takes 1 to 100 workspace ids per call.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string[]]$WorkspaceId,
        [switch]$DatasetSchema,
        [switch]$DatasetExpressions,
        [switch]$DatasourceDetails,
        [switch]$Lineage,
        [ValidateRange(1, 100)][int]$BatchSize = 100
    )
    $query = [ordered]@{}
    if ($DatasetExpressions) { $query.datasetExpressions = 'true' }
    if ($DatasetSchema)      { $query.datasetSchema = 'true' }
    if ($DatasourceDetails)  { $query.datasourceDetails = 'true' }
    if ($Lineage)            { $query.lineage = 'true' }
    $qs = if ($query.Count) { '?' + (($query.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join '&') } else { '' }
    $ids = @($WorkspaceId | Where-Object { $_ } | Select-Object -Unique)
    if ($ids.Count -eq 0) { throw 'No workspace ids given.' }
    for ($i = 0; $i -lt $ids.Count; $i += $BatchSize) {
        $last = [Math]::Min($i + $BatchSize, $ids.Count) - 1
        [pscustomobject]@{
            Method = 'POST'
            Uri    = "https://api.powerbi.com/v1.0/myorg/admin/workspaces/getInfo$qs"
            Body   = @{ workspaces = @($ids[$i..$last]) }
        }
    }
}

function Get-GovernanceFindings {
    <#
    .SYNOPSIS Evaluates scanner API output (admin/workspaces/scanResult) against policy.json and returns findings.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$ScanResultPath,
        [Parameter(Mandatory)][string]$PolicyPath
    )
    $scan = Read-JsonFile $ScanResultPath
    $policy = Read-JsonFile $PolicyPath
    $findings = [System.Collections.Generic.List[object]]::new()
    function Add-Finding($Rule, $Severity, $Workspace, $Kind, $Item, $Message) {
        $findings.Add([pscustomobject]@{ Rule = $Rule; Severity = $Severity; Workspace = $Workspace; ItemType = $Kind; Item = $Item; Message = $Message })
    }

    foreach ($ws in @($scan.workspaces)) {
        $isProd = $ws.name -match $policy.productionWorkspacePattern
        $datasets = @(Get-OptionalProperty $ws 'datasets')
        $reports = @(Get-OptionalProperty $ws 'reports')
        $certifiedIds = @($datasets | Where-Object { (Get-OptionalProperty (Get-OptionalProperty $_ 'endorsementDetails') 'endorsement') -eq 'Certified' } | ForEach-Object { $_.id })

        if ($policy.flagContentInPersonalWorkspaces -and $ws.type -eq 'PersonalGroup' -and ($datasets.Count + $reports.Count) -gt 0) {
            Add-Finding 'NoContentInPersonalWorkspace' 'Warning' $ws.name 'Workspace' $ws.name 'Personal workspace holds content that others cannot govern.'
        }
        if ($isProd -and $policy.requireDedicatedCapacityInProduction -and -not (Get-OptionalProperty $ws 'isOnDedicatedCapacity')) {
            Add-Finding 'ProdOnCapacity' 'Error' $ws.name 'Workspace' $ws.name 'Production workspace is not on a dedicated capacity.'
        }

        foreach ($ds in $datasets) {
            $end = Get-OptionalProperty (Get-OptionalProperty $ds 'endorsementDetails') 'endorsement'
            $by = Get-OptionalProperty (Get-OptionalProperty $ds 'endorsementDetails') 'certifiedBy'
            if ($policy.requireOwnerOnDatasets -and -not (Get-OptionalProperty $ds 'configuredBy') -and $ws.type -ne 'PersonalGroup') {
                Add-Finding 'OwnerRequired' 'Warning' $ws.name 'SemanticModel' $ds.name 'No configuredBy owner on the semantic model.'
            }
            if ($end -eq 'Certified' -and $by -and ($policy.certifiers -notcontains $by)) {
                Add-Finding 'CertifierNotAllowed' 'Error' $ws.name 'SemanticModel' $ds.name "Certified by $by, who is not in the policy certifier list."
            }
            if ($isProd) {
                if ($policy.requireCertifiedInProduction -and $end -ne 'Certified') {
                    Add-Finding 'ProdModelCertified' 'Error' $ws.name 'SemanticModel' $ds.name "Production semantic model is '$(if ($end) { $end } else { 'not endorsed' })', policy requires Certified."
                }
                if ($policy.requireSensitivityLabelInProduction -and -not (Get-OptionalProperty (Get-OptionalProperty $ds 'sensitivityLabel') 'labelId')) {
                    Add-Finding 'ProdLabelRequired' 'Error' $ws.name 'SemanticModel' $ds.name 'No sensitivity label.'
                }
            }
        }
        foreach ($r in $reports) {
            if ($isProd) {
                if ($policy.requireSensitivityLabelInProduction -and -not (Get-OptionalProperty (Get-OptionalProperty $r 'sensitivityLabel') 'labelId')) {
                    Add-Finding 'ProdLabelRequired' 'Error' $ws.name 'Report' $r.name 'No sensitivity label.'
                }
                if ($policy.reportsMustUseCertifiedModelInProduction -and $r.datasetId -and ($certifiedIds -notcontains $r.datasetId)) {
                    Add-Finding 'ReportOnUncertifiedModel' 'Error' $ws.name 'Report' $r.name 'Report is bound to a semantic model that is not certified.'
                }
            }
        }
    }
    $findings
}

function Get-RlsExpectedCounts {
    <#
    .SYNOPSIS From the mapping and per-department request counts, the number of requests each user should see through the role.
    .DESCRIPTION Mirrors the DAX in roles/DepartmentReader.tmdl: a user sees the departments listed for their UPN. Compare with Invoke-RlsCheck.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$MapCsv,
        [Parameter(Mandatory)][string]$CountsCsv
    )
    $counts = @{}
    foreach ($row in Import-Csv -LiteralPath $CountsCsv) { $counts[$row.DepartmentKey] = [int]$row.Requests }
    $out = [ordered]@{}
    foreach ($m in Import-Csv -LiteralPath $MapCsv) {
        if (-not $counts.ContainsKey($m.DepartmentKey)) { throw "Mapping row for unknown department '$($m.DepartmentKey)'." }
        $key = $m.UserPrincipalName.ToLowerInvariant()
        $out[$key] = [int]($(if ($out.Contains($key)) { $out[$key] } else { 0 })) + $counts[$m.DepartmentKey]
    }
    $out
}

function New-ExecuteQueriesBody {
    <#
    .SYNOPSIS Body for POST datasets/{id}/executeQueries. One query, one table. impersonatedUserName applies the RLS of that user.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Query,
        [string]$ImpersonatedUserName
    )
    if ($Query -notmatch '^\s*EVALUATE\b') { throw 'A DAX query for executeQueries must start with EVALUATE.' }
    $body = [ordered]@{ queries = @(@{ query = $Query }); serializerSettings = @{ includeNulls = $true } }
    if ($ImpersonatedUserName) { $body.impersonatedUserName = $ImpersonatedUserName }
    $body
}

function Invoke-RlsCheck {
    <#
    .SYNOPSIS Needs a tenant. Runs the row count as each mapped user and compares with Get-RlsExpectedCounts.
    .DESCRIPTION Token: pass -AccessToken, for example from `az account get-access-token --resource https://analysis.windows.net/powerbi/api`.
    The caller needs Build permission on the semantic model. Impersonation only applies RLS to the roles of Viewer-level access:
    workspace Admin, Member and Contributor bypass RLS, so test with a caller that is not one of them, or read the result with that in mind.
    A service principal cannot be used on a semantic model with RLS (Learn: Execute Queries limitations).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)][string]$DatasetId,
        [Parameter(Mandatory)][string]$MapCsv,
        [Parameter(Mandatory)][string]$CountsCsv,
        [string]$AccessToken
    )
    $expected = Get-RlsExpectedCounts -MapCsv $MapCsv -CountsCsv $CountsCsv
    foreach ($upn in $expected.Keys) {
        $body = New-ExecuteQueriesBody -Query 'EVALUATE ROW("Requests", [Requests])' -ImpersonatedUserName $upn
        $uri = "https://api.powerbi.com/v1.0/myorg/datasets/$DatasetId/executeQueries"
        $actual = $null
        if ($PSCmdlet.ShouldProcess($uri, "executeQueries as $upn")) {
            $resp = Invoke-RestMethod -Method Post -Uri $uri -Headers @{ Authorization = "Bearer $AccessToken" } `
                -ContentType 'application/json' -Body ($body | ConvertTo-Json -Depth 8)
            $row = $resp.results[0].tables[0].rows[0]
            $actual = [int]($row.PSObject.Properties | Select-Object -First 1).Value
        }
        [pscustomobject]@{ User = $upn; Expected = $expected[$upn]; Actual = $actual; Pass = ($actual -eq $expected[$upn]) }
    }
}

function New-DeployRequest {
    <#
    .SYNOPSIS Builds the body for POST deploymentPipelines/{id}/deploy (Fabric REST API). Selective deploy when -Item is given.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][guid]$SourceStageId,
        [Parameter(Mandatory)][guid]$TargetStageId,
        [object[]]$Item,
        [string]$Note
    )
    if ($SourceStageId -eq $TargetStageId) { throw 'Source and target stage must differ.' }
    if ($Note -and $Note.Length -gt 1024) { throw 'Note is limited to 1024 characters.' }
    $body = [ordered]@{ sourceStageId = "$SourceStageId"; targetStageId = "$TargetStageId" }
    if ($Item) {
        if ($Item.Count -gt 300) { throw 'A deploy request takes at most 300 items.' }
        $body.items = @($Item | ForEach-Object {
            if ($script:DeployItemTypes -notcontains $_.ItemType) { throw "Unsupported itemType '$($_.ItemType)'." }
            [ordered]@{ sourceItemId = "$([guid]$_.SourceItemId)"; itemType = $_.ItemType }
        })
    }
    if ($Note) { $body.note = $Note }
    $body
}

function Invoke-PipelineDeploy {
    <#
    .SYNOPSIS Needs a tenant (Fabric deployment pipeline, pipeline admin role). Starts a deployment and waits for the long running operation.
    .DESCRIPTION The API returns 202 with a Location header and Retry-After. The 10 calls per minute limit applies.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory)][guid]$PipelineId,
        [Parameter(Mandatory)][hashtable]$Body,
        [string]$AccessToken,
        [int]$TimeoutSeconds = 600
    )
    $uri = "https://api.fabric.microsoft.com/v1/deploymentPipelines/$PipelineId/deploy"
    if (-not $PSCmdlet.ShouldProcess($uri, 'Deploy stage content')) { return }
    $h = @{ Authorization = "Bearer $AccessToken" }
    $resp = Invoke-WebRequest -Method Post -Uri $uri -Headers $h -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Depth 8)
    if ([int]$resp.StatusCode -eq 200) { return ($resp.Content | ConvertFrom-Json) }
    $loc = @($resp.Headers['Location'])[0]
    $wait = [int](@($resp.Headers['Retry-After'])[0] ?? 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds $wait
        $state = Invoke-RestMethod -Method Get -Uri $loc -Headers $h
        if ($state.status -in 'Succeeded', 'Failed') { return $state }
    }
    throw "Deployment did not finish within $TimeoutSeconds seconds. Operation: $loc"
}

Export-ModuleMember -Function New-ScanRequest, Get-GovernanceFindings, Get-RlsExpectedCounts, New-ExecuteQueriesBody, Invoke-RlsCheck, New-DeployRequest, Invoke-PipelineDeploy
