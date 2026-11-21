<#
.SYNOPSIS
    Creates the ContosoInspections schema (publisher, solution, 4 tables, relationships, alternate key, the field-inspector
    security role, sample rows) in a Dataverse environment through the Web API. Idempotent: anything that already exists is skipped.

.DESCRIPTION
    Source of truth: ../schema/contosoinspections.schema.json, an exact copy of episode 12's schema (a test fails if the two
    files ever differ), so the canvas app (episode 11) and the model-driven app (episode 12) share one data model. Everything is created inside the solution through the
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
    [string] $SeedPath = (Join-Path $PSScriptRoot '../data/seed.json'),
    [string] $RoleName = 'Inspection Field Inspector',
    [switch] $SkipSecurityRole,
    [switch] $SeedData,
    [string] $AlexEmail,
    [string] $SamEmail
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ApiPath = '/api/data/v9.2'
$Lcid = 1033

# What the canvas app needs on top of the shared schema: Learn (set up mobile offline for canvas apps) says the inspector's role
# must also read the app and the offline system tables, and the tables themselves must be offline enabled.
$OfflinePrivileges = @(
    @{ Name = 'prvReadCanvasApp'; Depth = 'Global' }
    @{ Name = 'prvReadMobileOfflineProfile'; Depth = 'Global' }
    @{ Name = 'prvReadSyncError'; Depth = 'Global' }
)

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

function Test-Flag($Object, [string] $Name) { [bool]($Object.PSObject.Properties[$Name] -and $Object.$Name) }

function Get-OptionValue([int] $OptionValuePrefix, [int] $Value) { $OptionValuePrefix * 10000 + $Value }

function New-ColumnPayload($Column, [int] $OptionValuePrefix) {
    $common = @{
        SchemaName    = $Column.logicalName
        DisplayName   = New-Label $Column.displayName
        RequiredLevel = New-RequiredLevel (Test-Flag $Column 'required')
    }
    if (Test-Flag $Column 'secured') { $common.IsSecured = $true }

    switch ($Column.type) {
        { $_ -in 'string', 'email', 'phone' } {
            $format = @{ string = 'Text'; email = 'Email'; phone = 'Phone' }[$Column.type]
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
        'whole' {
            $min = if ($Column.PSObject.Properties['min']) { [int]$Column.min } else { -2147483648 }
            $max = if ($Column.PSObject.Properties['max']) { [int]$Column.max } else { 2147483647 }
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.IntegerAttributeMetadata'
                AttributeType = 'Integer'; AttributeTypeName = @{ Value = 'IntegerType' }
                Format = 'None'; MinValue = $min; MaxValue = $max
            }
        }
        'date' {
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.DateTimeAttributeMetadata'
                AttributeType = 'DateTime'; AttributeTypeName = @{ Value = 'DateTimeType' }
                Format = 'DateOnly'
            }
        }
        'bool' {
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.BooleanAttributeMetadata'
                AttributeType = 'Boolean'; AttributeTypeName = @{ Value = 'BooleanType' }
                DefaultValue = (Test-Flag $Column 'default')
                OptionSet = @{
                    '@odata.type' = 'Microsoft.Dynamics.CRM.BooleanOptionSetMetadata'
                    TrueOption = @{ Value = 1; Label = New-Label 'Yes' }
                    FalseOption = @{ Value = 0; Label = New-Label 'No' }
                    OptionSetType = 'Boolean'
                }
            }
        }
        'choice' {
            # Options are [label, value] pairs; the stored value is the publisher's option value prefix times 10000 plus the value.
            $options = @(foreach ($o in $Column.options) { @{ Value = (Get-OptionValue $OptionValuePrefix ([int]$o[1])); Label = New-Label ([string]$o[0]) } })
            $default = if ($Column.PSObject.Properties['default']) { [int]$Column.default } else { 0 }
            return $common + @{
                '@odata.type' = 'Microsoft.Dynamics.CRM.PicklistAttributeMetadata'
                AttributeType = 'Picklist'; AttributeTypeName = @{ Value = 'PicklistType' }
                DefaultFormValue = (Get-OptionValue $OptionValuePrefix $default)
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
        default { throw "Unknown column type '$($Column.type)' on $($Column.logicalName)" }
    }
}

function New-TablePayload($Table) {
    $primary = @{
        '@odata.type' = 'Microsoft.Dynamics.CRM.StringAttributeMetadata'
        AttributeType = 'String'; AttributeTypeName = @{ Value = 'StringType' }
        SchemaName = $Table.primaryName.logicalName; DisplayName = New-Label $Table.primaryName.displayName
        IsPrimaryName = $true; RequiredLevel = New-RequiredLevel $true
        FormatName = @{ Value = 'Text' }; MaxLength = [int]$Table.primaryName.maxLength
    }
    # The auto number is assigned by Dataverse when the row is saved: INS-00001, INS-00002, ...
    if (Test-Flag $Table.primaryName 'autoNumber') { $primary.AutoNumberFormat = $Table.primaryName.autoNumber }
    @{
        '@odata.type'         = 'Microsoft.Dynamics.CRM.EntityMetadata'
        SchemaName            = $Table.logicalName
        DisplayName           = New-Label $Table.displayName
        DisplayCollectionName = New-Label $Table.pluralName
        Description           = New-Label $Table.description
        OwnershipType         = $Table.ownership
        IsActivity            = $false; HasActivities = $false; HasNotes = $false
        IsQuickCreateEnabled  = (Test-Flag $Table 'quickCreate')
        IsAvailableOffline    = $true   # the canvas app runs offline: Learn requires offline-enabled tables
        Attributes            = @($primary)
    }
}

function Get-CascadeConfiguration($Rel) {
    $none = @{ Assign = 'NoCascade'; Delete = 'NoCascade'; Merge = 'NoCascade'; Reparent = 'NoCascade'; Share = 'NoCascade'; Unshare = 'NoCascade' }
    if (Test-Flag $Rel 'parental') {
        return @{ Assign = 'Cascade'; Delete = 'Cascade'; Merge = 'NoCascade'; Reparent = 'Cascade'; Share = 'Cascade'; Unshare = 'Cascade' }
    }
    if ($Rel.delete -notin 'Restrict', 'RemoveLink', 'Cascade') { throw "Unknown delete behavior '$($Rel.delete)' on $($Rel.name)" }
    $none.Delete = $Rel.delete
    $none
}

function New-RelationshipPayload($Rel, $Schema) {
    $referencing = $Schema.tables | Where-Object logicalName -eq $Rel.referencing
    $referenced = $Schema.tables | Where-Object logicalName -eq $Rel.referenced
    $lookup = $referencing.columns | Where-Object logicalName -eq $Rel.lookup
    @{
        '@odata.type' = 'Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata'
        SchemaName = $Rel.name
        ReferencedEntity = $Rel.referenced
        ReferencedAttribute = $Rel.referenced + 'id'
        ReferencingEntity = $Rel.referencing
        AssociatedMenuConfiguration = @{ Behavior = 'UseCollectionName'; Group = 'Details'; Label = New-Label $referencing.pluralName; Order = 10000 }
        CascadeConfiguration = Get-CascadeConfiguration $Rel
        Lookup = @{
            '@odata.type' = 'Microsoft.Dynamics.CRM.LookupAttributeMetadata'
            AttributeType = 'Lookup'; AttributeTypeName = @{ Value = 'LookupType' }
            SchemaName = $lookup.logicalName
            DisplayName = New-Label $lookup.displayName
            Description = New-Label "The $($referenced.displayName.ToLowerInvariant()) this $($referencing.displayName.ToLowerInvariant()) belongs to."
            RequiredLevel = New-RequiredLevel (Test-Flag $lookup 'required')
        }
    }
}

function Get-ProvisioningPlan($Schema) {
    $header = @{ 'MSCRM.SolutionUniqueName' = $Schema.solution.uniqueName }
    $prefix = [int]$Schema.publisher.optionValuePrefix
    $lookupColumns = @($Schema.relationships | ForEach-Object { $_.lookup })
    foreach ($table in $Schema.tables) {
        [pscustomobject]@{
            Kind = 'Table'; Name = $table.logicalName; Method = 'POST'; Path = '/EntityDefinitions'
            ExistsPath = "/EntityDefinitions(LogicalName='$($table.logicalName)')?`$select=MetadataId"
            Headers = $header; Body = New-TablePayload $table
        }
    }
    foreach ($table in $Schema.tables) {
        foreach ($column in $table.columns) {
            if ($column.type -eq 'lookup') { continue }   # lookups are created with their relationship, below
            [pscustomobject]@{
                Kind = 'Column'; Name = "$($table.logicalName).$($column.logicalName)"; Method = 'POST'
                Path = "/EntityDefinitions(LogicalName='$($table.logicalName)')/Attributes"
                ExistsPath = "/EntityDefinitions(LogicalName='$($table.logicalName)')/Attributes(LogicalName='$($column.logicalName)')?`$select=MetadataId"
                Headers = $header; Body = New-ColumnPayload $column $prefix
            }
        }
    }
    foreach ($rel in $Schema.relationships) {
        [pscustomobject]@{
            Kind = 'Relationship'; Name = $rel.name; Method = 'POST'; Path = '/RelationshipDefinitions'
            ExistsPath = "/RelationshipDefinitions(SchemaName='$($rel.name)')?`$select=MetadataId"
            Headers = $header; Body = New-RelationshipPayload $rel $Schema
        }
    }
    foreach ($table in $Schema.tables) {
        if (-not $table.PSObject.Properties['alternateKeys']) { continue }
        foreach ($key in $table.alternateKeys) {
            [pscustomobject]@{
                Kind = 'Key'; Name = $key.name; Method = 'POST'; Path = "/EntityDefinitions(LogicalName='$($table.logicalName)')/Keys"
                ExistsPath = "/EntityDefinitions(LogicalName='$($table.logicalName)')/Keys?`$select=SchemaName"; ExistsKey = $key.name
                Headers = $header
                Body = @{
                    '@odata.type' = 'Microsoft.Dynamics.CRM.EntityKeyMetadata'
                    SchemaName = $key.name; DisplayName = New-Label $key.displayName; KeyAttributes = @($key.columns)
                }
            }
        }
    }
}

function Get-RolePrivilegeRequests($Role) {
    foreach ($table in $Role.privileges.PSObject.Properties) {
        foreach ($verb in $table.Value.PSObject.Properties) {
            [pscustomobject]@{ Table = $table.Name; Name = "prv$($verb.Name)$($table.Name)"; Depth = $verb.Value }
        }
    }
    foreach ($extra in $OfflinePrivileges) { [pscustomobject]@{ Table = 'offline'; Name = $extra.Name; Depth = $extra.Depth } }
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

function Test-Exists([string] $Path, [string] $KeyName) {
    $found = Invoke-Dv -Method GET -Path $Path -AllowNotFound
    if ($null -eq $found) { return $false }
    # Keys come back as a list: look for ours by schema name.
    if ($KeyName -and $found.PSObject.Properties['value']) { return @($found.value | Where-Object SchemaName -eq $KeyName).Count -gt 0 }
    $true
}

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
$role = @($schema.security.roles | Where-Object name -eq $RoleName)[0]
if (-not $SkipSecurityRole -and -not $role) { throw "Role '$RoleName' is not in the schema." }

if ($PlanOnly) {
    Write-Host "Plan for solution $($schema.solution.uniqueName) (publisher prefix $($schema.publisher.prefix)): nothing is sent."
    foreach ($step in $plan) {
        $what = switch ($step.Kind) {
            'Column' { $step.Path.Replace('/Attributes', '') + ' + ' + $step.Body.SchemaName }
            'Relationship' { $step.Name + ' (adds lookup ' + $step.Body.Lookup.SchemaName + ')' }
            default { $step.Name }
        }
        '{0,-13} {1,-10} {2}' -f $step.Kind, $step.Method, $what
    }
    'Publisher     GET/POST   /publishers ({0})' -f $schema.publisher.uniqueName
    'Solution      GET/POST   /solutions ({0})' -f $schema.solution.uniqueName
    if (-not $SkipSecurityRole) {
        'SecurityRole GET/POST   /roles ({0}), {1} privileges, AddSolutionComponent' -f $role.name, @(Get-RolePrivilegeRequests $role).Count
    }
    'Publish       POST       /PublishAllXml'
    return
}

if (-not $AccessToken) { throw 'No access token. Set DATAVERSE_ACCESS_TOKEN or pass -AccessToken (this script never signs in).' }

Write-Host "Provisioning $($schema.solution.uniqueName) in $EnvironmentUrl"

# 1. Publisher and solution (the solution is what the header below points at).
$publisher = $schema.publisher
$publisherId = Find-Or-Create -Set 'publishers' -Filter "uniquename eq '$($publisher.uniqueName)'" -IdProperty 'publisherid' -What "publisher $($publisher.uniqueName)" -Body @{
    uniquename = $publisher.uniqueName; friendlyname = $publisher.displayName; description = $publisher.description
    customizationprefix = $publisher.prefix; customizationoptionvalueprefix = [int]$publisher.optionValuePrefix
}
$null = Find-Or-Create -Set 'solutions' -Filter "uniquename eq '$($schema.solution.uniqueName)'" -IdProperty 'solutionid' -What "solution $($schema.solution.uniqueName)" -Body @{
    uniquename = $schema.solution.uniqueName; friendlyname = $schema.solution.displayName; description = $schema.solution.description
    version = $schema.version
    'publisherid@odata.bind' = "/publishers($publisherId)"
}

# 2. Tables, columns, relationships (with their lookups), alternate key: in plan order, skipping what exists.
foreach ($step in $plan) {
    $keyName = if ($step.PSObject.Properties['ExistsKey']) { $step.ExistsKey } else { '' }
    if (Test-Exists $step.ExistsPath $keyName) { Write-Host "  exists   $($step.Kind) $($step.Name)"; continue }
    Write-Host "  create   $($step.Kind) $($step.Name)"
    $null = Invoke-Dv -Method $step.Method -Path $step.Path -Body $step.Body -Headers $step.Headers
}

# 3. Security role: the field inspector's (the back-office role belongs to episode 12's solution).
if (-not $SkipSecurityRole) {
    $root = (Invoke-Dv -Method GET -Path '/businessunits?$filter=parentbusinessunitid eq null&$select=businessunitid').value
    $rootId = @($root)[0].businessunitid
    $roleId = Find-Or-Create -Set 'roles' -Filter "name eq '$($role.name)' and _businessunitid_value eq $rootId" -IdProperty 'roleid' -What "role $($role.name)" -Body @{
        name = $role.name; description = $role.description; 'businessunitid@odata.bind' = "/businessunits($rootId)"
    }
    $privileges = foreach ($req in (Get-RolePrivilegeRequests $role)) {
        $found = (Invoke-Dv -Method GET -Path "/privileges?`$select=privilegeid,name&`$filter=name eq '$($req.Name)'").value
        if (-not $found -or @($found).Count -eq 0) { throw "Privilege $($req.Name) not found. Add it in the role editor (Customization tab for system tables) and re-run." }
        @{ PrivilegeId = @($found)[0].privilegeid; Depth = $req.Depth; BusinessUnitId = $rootId }
    }
    Write-Host "  add      $(@($privileges).Count) privileges to $($role.name)"
    $null = Invoke-Dv -Method POST -Path "/roles($roleId)/Microsoft.Dynamics.CRM.AddPrivilegesRole" -Body @{ Privileges = @($privileges) }
    # ComponentType 20 = Security Role (Learn: solutioncomponent table, componenttype choices).
    $null = Invoke-Dv -Method POST -Path '/AddSolutionComponent' -Body @{
        ComponentId = $roleId; ComponentType = 20; SolutionUniqueName = $schema.solution.uniqueName; AddRequiredComponents = $false
    }
}

# 4. Publish so apps see the new tables.
Write-Host '  publish  all customizations'
$null = Invoke-Dv -Method POST -Path '/PublishAllXml' -Body @{}

# 5. Optional sample rows (idempotent on the site code / email, so episode 12's own sample rows are never duplicated).
if ($SeedData) {
    $seed = Get-Content -LiteralPath $SeedPath -Raw | ConvertFrom-Json
    $prefix = [int]$schema.publisher.optionValuePrefix
    $siteTable = $schema.tables | Where-Object logicalName -eq 'cin_site'
    $riskOptions = @(($siteTable.columns | Where-Object logicalName -eq 'cin_risklevel').options)
    foreach ($site in $seed.sites) {
        $risk = @($riskOptions | Where-Object { $_[0] -eq $site.risk })[0]
        if (-not $risk) { throw "Unknown risk level '$($site.risk)' for site $($site.code)" }
        $null = Find-Or-Create -Set 'cin_sites' -Filter "cin_sitecode eq '$($site.code)'" -IdProperty 'cin_siteid' -What "site $($site.code)" -Body @{
            cin_name = $site.name; cin_sitecode = $site.code; cin_address = $site.address; cin_city = $site.city
            cin_risklevel = (Get-OptionValue $prefix ([int]$risk[1]))
        }
    }
    foreach ($inspector in $seed.inspectors) {
        $email = if ($inspector.emailParameter -eq 'AlexEmail' -and $AlexEmail) { $AlexEmail }
        elseif ($inspector.emailParameter -eq 'SamEmail' -and $SamEmail) { $SamEmail }
        else { $inspector.defaultEmail }
        $null = Find-Or-Create -Set 'cin_inspectors' -Filter "cin_email eq '$email'" -IdProperty 'cin_inspectorid' -What "inspector $($inspector.name)" -Body @{
            cin_name = $inspector.name; cin_email = $email; cin_phone = $inspector.phone; cin_certified = [bool]$inspector.certified
        }
    }
}

Write-Host 'Done.'
