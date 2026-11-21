<#
.SYNOPSIS
    Creates the ContosoInspections schema (publisher, solution, 4 tables, relationships, security role, sample rows)
    in a Dataverse environment through the Web API. Idempotent: anything that already exists is skipped.

.DESCRIPTION
    Source of truth: ../schema/contosoinspections.schema.json. Everything is created inside the solution through the
    MSCRM.SolutionUniqueName header (Learn: "Create and update table definitions by using the Web API"), so the solution
    can be exported afterwards with `pac solution export` and unpacked into ../solution.

    The script never signs in. Pass a bearer token for the environment (for example from `az account get-access-token
    --resource <environment url> --query accessToken -o tsv`, which the recorder runs after signing in as the lab admin)
    or set DATAVERSE_ACCESS_TOKEN. `-PlanOnly` prints the metadata requests without calling anything and needs no token.

.EXAMPLE
    ./Provision-ContosoInspections.ps1 -EnvironmentUrl https://contoso-dev.crm4.dynamics.com -PlanOnly

.EXAMPLE
    $env:DATAVERSE_ACCESS_TOKEN = (az account get-access-token --resource https://contoso-dev.crm4.dynamics.com --query accessToken -o tsv)
    ./Provision-ContosoInspections.ps1 -EnvironmentUrl https://contoso-dev.crm4.dynamics.com -SeedData -AlexEmail alex.demo@contoso.com
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $EnvironmentUrl,
    [string] $SchemaPath = (Join-Path $PSScriptRoot '../schema/contosoinspections.schema.json'),
    [string] $AccessToken = $env:DATAVERSE_ACCESS_TOKEN,
    [switch] $PlanOnly,
    [switch] $SkipSecurityRole,
    [switch] $SeedData,
    [string] $AlexEmail,
    [string] $SamEmail
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ApiPath = '/api/data/v9.2'
$Lcid = 1033

#region payload builders (pure functions: the tests call these without any service)

function New-Label([string] $Text) {
    @{
        '@odata.type'   = 'Microsoft.Dynamics.CRM.Label'
        LocalizedLabels = @(@{ '@odata.type' = 'Microsoft.Dynamics.CRM.LocalizedLabel'; Label = $Text; LanguageCode = $Lcid })
    }
}

function New-RequiredLevel([bool] $Required) {
    @{
        Value = $(if ($Required) { 'ApplicationRequired' } else { 'None' })
        CanBeChanged = $true
        ManagedPropertyLogicalName = 'canmodifyrequirementlevelsettings'
    }
}

function Get-OptionValue([int] $OptionValuePrefix, [int] $Index) { $OptionValuePrefix * 10000 + $Index }

function New-ColumnPayload($Column, [int] $OptionValuePrefix) {
    $common = @{
        SchemaName    = $Column.schemaName
        DisplayName   = New-Label $Column.displayName
        RequiredLevel = New-RequiredLevel ([bool]($Column.PSObject.Properties['required'] -and $Column.required))
    }
    if ($Column.PSObject.Properties['description'] -and $Column.description) { $common.Description = New-Label $Column.description }

    switch ($Column.type) {
        'string' {
            $format = if ($Column.PSObject.Properties['format'] -and $Column.format) { $Column.format } else { 'Text' }
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.StringAttributeMetadata'
                AttributeType = 'String'; AttributeTypeName = @{ Value = 'StringType' }
                FormatName = @{ Value = $format }; MaxLength = [int]$Column.maxLength
            }
        }
        'memo' {
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.MemoAttributeMetadata'
                AttributeType = 'Memo'; AttributeTypeName = @{ Value = 'MemoType' }
                Format = 'TextArea'; MaxLength = [int]$Column.maxLength
            }
        }
        'date' {
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.DateTimeAttributeMetadata'
                AttributeType = 'DateTime'; AttributeTypeName = @{ Value = 'DateTimeType' }
                Format = 'DateOnly'
            }
        }
        'boolean' {
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.BooleanAttributeMetadata'
                AttributeType = 'Boolean'; AttributeTypeName = @{ Value = 'BooleanType' }
                DefaultValue = [bool]$Column.default
                OptionSet = @{
                    '@odata.type' = 'Microsoft.Dynamics.CRM.BooleanOptionSetMetadata'
                    TrueOption = @{ Value = 1; Label = New-Label $Column.trueLabel }
                    FalseOption = @{ Value = 0; Label = New-Label $Column.falseLabel }
                    OptionSetType = 'Boolean'
                }
            }
        }
        'choice' {
            $options = @(for ($i = 0; $i -lt @($Column.options).Count; $i++) {
                    @{ Value = (Get-OptionValue $OptionValuePrefix $i); Label = New-Label $Column.options[$i] }
                })
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.PicklistAttributeMetadata'
                AttributeType = 'Picklist'; AttributeTypeName = @{ Value = 'PicklistType' }
                OptionSet = @{ '@odata.type' = 'Microsoft.Dynamics.CRM.OptionSetMetadata'; Options = $options; IsGlobal = $false; OptionSetType = 'Picklist' }
            }
        }
        'image' {
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.ImageAttributeMetadata'
                AttributeTypeName = @{ Value = 'ImageType' }
                MaxSizeInKB = [int]$Column.maxSizeKB; CanStoreFullImage = $true
            }
        }
        default { throw "Unknown column type '$($Column.type)' on $($Column.schemaName)" }
    }
}

function New-TablePayload($Table) {
    $primary = @{
        '@odata.type' = 'Microsoft.Dynamics.CRM.StringAttributeMetadata'
        AttributeType = 'String'; AttributeTypeName = @{ Value = 'StringType' }
        SchemaName = $Table.primaryName.schemaName; DisplayName = New-Label $Table.primaryName.displayName
        IsPrimaryName = $true; RequiredLevel = New-RequiredLevel $true
        FormatName = @{ Value = 'Text' }; MaxLength = [int]$Table.primaryName.maxLength
    }
    @{
        '@odata.type'         = 'Microsoft.Dynamics.CRM.EntityMetadata'
        SchemaName            = $Table.schemaName
        DisplayName           = New-Label $Table.displayName
        DisplayCollectionName = New-Label $Table.pluralName
        Description           = New-Label $Table.description
        OwnershipType         = $Table.ownership
        IsActivity            = $false; HasActivities = $false; HasNotes = $false
        IsAvailableOffline    = [bool]$Table.availableOffline
        Attributes            = @($primary)
    }
}

function Get-CascadeConfiguration([string] $Kind) {
    switch ($Kind) {
        'Parental' { @{ Assign = 'Cascade'; Delete = 'Cascade'; Merge = 'NoCascade'; Reparent = 'Cascade'; Share = 'Cascade'; Unshare = 'Cascade' } }
        'Referential' { @{ Assign = 'NoCascade'; Delete = 'Restrict'; Merge = 'NoCascade'; Reparent = 'NoCascade'; Share = 'NoCascade'; Unshare = 'NoCascade' } }
        default { throw "Unknown cascade kind '$Kind'" }
    }
}

function New-RelationshipPayload($Rel, $Schema) {
    $referencing = $Schema.tables | Where-Object schemaName -eq $Rel.referencing
    $referenced = $Schema.tables | Where-Object schemaName -eq $Rel.referenced
    $plural = $referencing.pluralName
    @{
        '@odata.type' = 'Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata'
        SchemaName = $Rel.schemaName
        ReferencedEntity = $Rel.referenced.ToLowerInvariant()
        ReferencedAttribute = $Rel.referenced.ToLowerInvariant() + 'id'
        ReferencingEntity = $Rel.referencing.ToLowerInvariant()
        AssociatedMenuConfiguration = @{ Behavior = 'UseCollectionName'; Group = 'Details'; Label = New-Label $plural; Order = 10000 }
        CascadeConfiguration = Get-CascadeConfiguration $Rel.cascade
        Lookup = @{
            '@odata.type' = 'Microsoft.Dynamics.CRM.LookupAttributeMetadata'
            AttributeType = 'Lookup'; AttributeTypeName = @{ Value = 'LookupType' }
            SchemaName = $Rel.lookup.schemaName
            DisplayName = New-Label $Rel.lookup.displayName
            Description = New-Label "The $($referenced.displayName.ToLowerInvariant()) this $($referencing.displayName.ToLowerInvariant()) belongs to."
            RequiredLevel = New-RequiredLevel ([bool]$Rel.lookup.required)
        }
    }
}

function Get-ProvisioningPlan($Schema) {
    $header = @{ 'MSCRM.SolutionUniqueName' = $Schema.solution.uniqueName }
    $prefix = [int]$Schema.solution.publisher.optionValuePrefix
    foreach ($table in $Schema.tables) {
        $logical = $table.schemaName.ToLowerInvariant()
        [pscustomobject]@{
            Kind = 'Table'; Name = $logical; Method = 'POST'; Path = '/EntityDefinitions'
            ExistsPath = "/EntityDefinitions(LogicalName='$logical')?`$select=MetadataId"
            Headers = $header; Body = New-TablePayload $table
        }
    }
    foreach ($table in $Schema.tables) {
        $logical = $table.schemaName.ToLowerInvariant()
        foreach ($column in $table.columns) {
            $columnLogical = $column.schemaName.ToLowerInvariant()
            [pscustomobject]@{
                Kind = 'Column'; Name = "$logical.$columnLogical"; Method = 'POST'
                Path = "/EntityDefinitions(LogicalName='$logical')/Attributes"
                ExistsPath = "/EntityDefinitions(LogicalName='$logical')/Attributes(LogicalName='$columnLogical')?`$select=MetadataId"
                Headers = $header; Body = New-ColumnPayload $column $prefix
            }
        }
    }
    foreach ($rel in $Schema.relationships) {
        [pscustomobject]@{
            Kind = 'Relationship'; Name = $rel.schemaName; Method = 'POST'; Path = '/RelationshipDefinitions'
            ExistsPath = "/RelationshipDefinitions(SchemaName='$($rel.schemaName)')?`$select=MetadataId"
            Headers = $header; Body = New-RelationshipPayload $rel $Schema
        }
    }
}

function Get-RolePrivilegeRequests($Schema) {
    foreach ($entry in $Schema.securityRole.privileges) {
        foreach ($property in $entry.PSObject.Properties) {
            if ($property.Name -in 'table', 'schemaName', 'why') { continue }
            [pscustomobject]@{ Table = $entry.table; Name = "prv$($property.Name)$($entry.schemaName)"; Depth = $property.Value }
        }
    }
}

#endregion

#region Web API plumbing

function Invoke-Dv {
    param([string] $Method, [string] $Path, $Body, [hashtable] $Headers = @{}, [switch] $AllowNotFound)
    $uri = $EnvironmentUrl.TrimEnd('/') + $ApiPath + $Path
    $all = @{
        Authorization = "Bearer $AccessToken"; Accept = 'application/json'
        'OData-MaxVersion' = '4.0'; 'OData-Version' = '4.0'
    } + $Headers
    $req = @{ Method = $Method; Uri = $uri; Headers = $all }
    if ($null -ne $Body) {
        $req.Body = ($Body | ConvertTo-Json -Depth 30 -Compress)
        $req.ContentType = 'application/json; charset=utf-8'
    }
    try { Invoke-RestMethod @req }
    catch {
        $status = if ($_.Exception.PSObject.Properties['Response'] -and $_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        if ($AllowNotFound -and $status -eq 404) { return $null }
        throw
    }
}

function Test-Exists([string] $Path) { $null -ne (Invoke-Dv -Method GET -Path $Path -AllowNotFound) }

function Find-Or-Create([string] $Set, [string] $Filter, $Body, [string] $IdProperty, [string] $What) {
    $found = Invoke-Dv -Method GET -Path "/$($Set)?`$filter=$Filter&`$select=$IdProperty"
    if ($found.value -and @($found.value).Count -gt 0) { Write-Host "  exists   $What"; return @($found.value)[0].$IdProperty }
    Write-Host "  create   $What"
    $created = Invoke-Dv -Method POST -Path "/$Set" -Body $Body -Headers @{ Prefer = 'return=representation' }
    $created.$IdProperty
}

#endregion

$schema = Get-Content -LiteralPath $SchemaPath -Raw | ConvertFrom-Json
$plan = @(Get-ProvisioningPlan $schema)

if ($PlanOnly) {
    Write-Host "Plan for solution $($schema.solution.uniqueName) (publisher prefix $($schema.solution.publisher.prefix)): nothing is sent."
    $plan | ForEach-Object { '{0,-13} {1,-10} {2}' -f $_.Kind, $_.Method, $(if ($_.Kind -eq 'Column') { $_.Path.Replace('/Attributes', '') + ' + ' + $_.Body.SchemaName } else { $_.Name }) }
    'Publisher     GET/POST   /publishers ({0})' -f $schema.solution.publisher.uniqueName
    'Solution      GET/POST   /solutions ({0})' -f $schema.solution.uniqueName
    if (-not $SkipSecurityRole) {
        'SecurityRole GET/POST   /roles ({0}), {1} privileges, AddSolutionComponent' -f $schema.securityRole.name, @(Get-RolePrivilegeRequests $schema).Count
    }
    'Publish       POST       /PublishAllXml'
    return
}

if (-not $AccessToken) { throw 'No access token. Set DATAVERSE_ACCESS_TOKEN or pass -AccessToken (this script never signs in).' }

Write-Host "Provisioning $($schema.solution.uniqueName) in $EnvironmentUrl"

# 1. Publisher and solution (the solution is what the header below points at).
$publisher = $schema.solution.publisher
$publisherId = Find-Or-Create -Set 'publishers' -Filter "uniquename eq '$($publisher.uniqueName)'" -IdProperty 'publisherid' -What "publisher $($publisher.uniqueName)" -Body @{
    uniquename = $publisher.uniqueName; friendlyname = $publisher.friendlyName
    customizationprefix = $publisher.prefix; customizationoptionvalueprefix = [int]$publisher.optionValuePrefix
}
$null = Find-Or-Create -Set 'solutions' -Filter "uniquename eq '$($schema.solution.uniqueName)'" -IdProperty 'solutionid' -What "solution $($schema.solution.uniqueName)" -Body @{
    uniquename = $schema.solution.uniqueName; friendlyname = $schema.solution.friendlyName; version = $schema.solution.version
    'publisherid@odata.bind' = "/publishers($publisherId)"
}

# 2. Tables, columns, relationships: in plan order, skipping what exists.
foreach ($step in $plan) {
    if (Test-Exists $step.ExistsPath) { Write-Host "  exists   $($step.Kind) $($step.Name)"; continue }
    Write-Host "  create   $($step.Kind) $($step.Name)"
    $null = Invoke-Dv -Method $step.Method -Path $step.Path -Body $step.Body -Headers $step.Headers
}

# 3. Security role.
if (-not $SkipSecurityRole) {
    $root = (Invoke-Dv -Method GET -Path '/businessunits?$filter=parentbusinessunitid eq null&$select=businessunitid').value
    $rootId = @($root)[0].businessunitid
    $roleName = $schema.securityRole.name
    $roleId = Find-Or-Create -Set 'roles' -Filter "name eq '$roleName' and _businessunitid_value eq $rootId" -IdProperty 'roleid' -What "role $roleName" -Body @{
        name = $roleName; description = $schema.securityRole.description; 'businessunitid@odata.bind' = "/businessunits($rootId)"
    }
    $privileges = foreach ($req in (Get-RolePrivilegeRequests $schema)) {
        $found = (Invoke-Dv -Method GET -Path "/privileges?`$select=privilegeid,name&`$filter=name eq '$($req.Name)'").value
        if (-not $found -or @($found).Count -eq 0) { throw "Privilege $($req.Name) not found. Add it in the role editor (Customization tab for system tables) and re-run." }
        @{ PrivilegeId = @($found)[0].privilegeid; Depth = $req.Depth; BusinessUnitId = $rootId }
    }
    Write-Host "  add      $(@($privileges).Count) privileges to $roleName"
    $null = Invoke-Dv -Method POST -Path "/roles($roleId)/Microsoft.Dynamics.CRM.AddPrivilegesRole" -Body @{ Privileges = @($privileges) }
    # ComponentType 20 = Security Role (Learn: solutioncomponent table, componenttype choices).
    $null = Invoke-Dv -Method POST -Path '/AddSolutionComponent' -Body @{
        ComponentId = $roleId; ComponentType = 20; SolutionUniqueName = $schema.solution.uniqueName; AddRequiredComponents = $false
    }
}

# 4. Publish so apps see the new tables.
Write-Host '  publish  all customizations'
$null = Invoke-Dv -Method POST -Path '/PublishAllXml' -Body @{}

# 5. Optional sample rows (idempotent on the code / email).
if ($SeedData) {
    $prefix = [int]$schema.solution.publisher.optionValuePrefix
    $siteTable = $schema.tables | Where-Object schemaName -eq 'cin_Site'
    $riskOptions = @(($siteTable.columns | Where-Object schemaName -eq 'cin_RiskRating').options)
    foreach ($site in $schema.sampleData.sites) {
        $null = Find-Or-Create -Set 'cin_sites' -Filter "cin_sitecode eq '$($site.code)'" -IdProperty 'cin_siteid' -What "site $($site.code)" -Body @{
            cin_name = $site.name; cin_sitecode = $site.code; cin_city = $site.city
            cin_riskrating = (Get-OptionValue $prefix ([array]::IndexOf($riskOptions, $site.risk)))
        }
    }
    foreach ($inspector in $schema.sampleData.inspectors) {
        $email = if ($inspector.emailParameter -eq 'AlexEmail' -and $AlexEmail) { $AlexEmail }
        elseif ($inspector.emailParameter -eq 'SamEmail' -and $SamEmail) { $SamEmail }
        else { $inspector.defaultEmail }
        $null = Find-Or-Create -Set 'cin_inspectors' -Filter "cin_workemail eq '$email'" -IdProperty 'cin_inspectorid' -What "inspector $($inspector.name)" -Body @{
            cin_name = $inspector.name; cin_workemail = $email; cin_region = $inspector.region; cin_certified = [bool]$inspector.certified
        }
    }
}

Write-Host 'Done.'
