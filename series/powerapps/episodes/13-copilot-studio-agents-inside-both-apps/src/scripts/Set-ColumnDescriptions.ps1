<#
.SYNOPSIS
    Writes the column descriptions in ../data/column-descriptions.json into Dataverse, so the Copilot Studio Dataverse knowledge
    source can match questions to columns. Learn (Add Dataverse tables as a knowledge source): Dataverse sources use table metadata
    and column descriptions for search-time matching.

.DESCRIPTION
    Learn (Create and update column definitions using the Web API): metadata is updated with PUT and the whole definition, never
    PATCH. So for each column the script GETs the full attribute, changes Description, PUTs it back with MSCRM.MergeLabels: true,
    and finally calls PublishXml. Never signs in: pass a token (DATAVERSE_ACCESS_TOKEN). -PlanOnly prints the requests, no token.

.EXAMPLE
    ./Set-ColumnDescriptions.ps1 -EnvironmentUrl https://contoso-dev.crm4.dynamics.com -PlanOnly
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $EnvironmentUrl,
    [string] $DescriptionsPath = (Join-Path $PSScriptRoot '../data/column-descriptions.json'),
    [string] $SchemaPath = (Join-Path $PSScriptRoot '../schema/contosoinspections.schema.json'),
    [string] $AccessToken = $env:DATAVERSE_ACCESS_TOKEN,
    [switch] $PlanOnly
)
$ErrorActionPreference = 'Stop'
$base = $EnvironmentUrl.TrimEnd('/') + '/api/data/v9.2'
$typeFor = @{ string = 'String'; email = 'String'; phone = 'String'; memo = 'Memo'; bool = 'Boolean'; date = 'DateTime'; whole = 'Integer'; choice = 'Picklist'; lookup = 'Lookup'; image = 'Image' }

function Get-Plan {
    $schema = Get-Content -Raw $SchemaPath | ConvertFrom-Json
    $descriptions = Get-Content -Raw $DescriptionsPath | ConvertFrom-Json
    foreach ($table in $descriptions.PSObject.Properties) {
        $tableSchema = $schema.tables | Where-Object logicalName -eq $table.Name
        if (-not $tableSchema) { throw "Table $($table.Name) is not in the schema." }
        foreach ($col in $table.Value.PSObject.Properties) {
            $colSchema = $tableSchema.columns | Where-Object logicalName -eq $col.Name
            if (-not $colSchema) { throw "Column $($table.Name).$($col.Name) is not in the schema." }
            [pscustomobject]@{
                Table = $table.Name; Column = $col.Name; Description = [string]$col.Value
                Uri = "$base/EntityDefinitions(LogicalName='$($table.Name)')/Attributes(LogicalName='$($col.Name)')/Microsoft.Dynamics.CRM.$($typeFor[$colSchema.type])AttributeMetadata"
            }
        }
    }
}

$plan = @(Get-Plan)
if ($PlanOnly) {
    foreach ($p in $plan) {
        "GET  $($p.Uri)"
        "PUT  $($p.Uri -replace '/Microsoft\.Dynamics\.CRM\.\w+$', '')   (Description = '$($p.Description)', MSCRM.MergeLabels: true)"
    }
    "POST $base/PublishXml   (ParameterXml: entities $((($plan | Select-Object -ExpandProperty Table -Unique) | ForEach-Object { $_ }) -join ', '))"
    return
}
if (-not $AccessToken) { throw 'Pass -AccessToken or set DATAVERSE_ACCESS_TOKEN (the recorder gets it with az account get-access-token).' }
$headers = @{ Authorization = "Bearer $AccessToken"; 'OData-MaxVersion' = '4.0'; 'OData-Version' = '4.0'; Accept = 'application/json'; 'If-None-Match' = 'null' }
foreach ($p in $plan) {
    $attr = Invoke-RestMethod -Method Get -Uri $p.Uri -Headers $headers
    if ($attr.Description.UserLocalizedLabel.Label -eq $p.Description) { Write-Verbose "$($p.Table).$($p.Column) already described"; continue }
    $attr.Description = @{ LocalizedLabels = @(@{ '@odata.type' = 'Microsoft.Dynamics.CRM.LocalizedLabel'; Label = $p.Description; LanguageCode = 1033 }) }
    if ($PSCmdlet.ShouldProcess("$($p.Table).$($p.Column)", 'Set description')) {
        $put = $headers + @{ 'MSCRM.MergeLabels' = 'true'; 'Content-Type' = 'application/json' }
        $put.Remove('If-None-Match')
        Invoke-RestMethod -Method Put -Uri ($p.Uri -replace '/Microsoft\.Dynamics\.CRM\.\w+$', '') -Headers $put -Body ($attr | ConvertTo-Json -Depth 20) | Out-Null
    }
}
$tables = ($plan | Select-Object -ExpandProperty Table -Unique | ForEach-Object { "<entity>$_</entity>" }) -join ''
$body = @{ ParameterXml = "<importexportxml><entities>$tables</entities></importexportxml>" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/PublishXml" -Headers ($headers + @{ 'Content-Type' = 'application/json' }) -Body $body | Out-Null
