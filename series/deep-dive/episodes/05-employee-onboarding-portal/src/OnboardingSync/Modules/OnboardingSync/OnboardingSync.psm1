# OnboardingSync: reads approved onboarding requests from a SharePoint list and hands them to the Microsoft Entra
# API-driven inbound provisioning service (SCIM /bulkUpload). It never creates users itself: the provisioning service
# matches on externalId -> employeeId, creates or updates the account, and Lifecycle Workflows take over from there.
#
# Graph permissions of the function's managed identity (application):
#   SynchronizationData-User.Upload           POST .../synchronization/jobs/{id}/bulkUpload
#   User.Read.All                             find users by employeeId / UPN, read the manager's employeeId
#   Lists.SelectedOperations.Selected         + a 'write' grant on the two lists only (provision/Grant-OnboardingAccess.ps1)

Set-StrictMode -Version 3.0

$script:GraphRoot = 'https://graph.microsoft.com/'
$script:GraphBase = 'https://graph.microsoft.com/v1.0'
$script:TokenCache = $null
$script:ScimCustomSchema = 'urn:ietf:params:scim:schemas:extension:contoso:1.0:User'
$script:ScimEnterpriseSchema = 'urn:ietf:params:scim:schemas:extension:enterprise:2.0:User'

class OnbValidationException : System.Exception {
    OnbValidationException([string] $message) : base($message) {}
}

#region Pure functions (no I/O) ---------------------------------------------------------------------------------------

function ConvertTo-OnbAsciiName {
    <# Lower-case ASCII for a UPN local part: strips accents ("João" -> "joao"), maps letters FormD can't split,
       drops everything that isn't a-z, 0-9 or '-'. Learn: a UPN can't contain accent characters. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [AllowEmptyString()] [string] $Text)

    $map = @{ 'ß' = 'ss'; 'æ' = 'ae'; 'œ' = 'oe'; 'ø' = 'o'; 'đ' = 'd'; 'ł' = 'l'; 'þ' = 'th' }
    $lower = $Text.Trim().ToLowerInvariant()
    foreach ($k in $map.Keys) { $lower = $lower.Replace($k, $map[$k]) }
    $sb = [System.Text.StringBuilder]::new()
    foreach ($ch in $lower.Normalize([System.Text.NormalizationForm]::FormD).ToCharArray()) {
        if ([System.Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch) -eq [System.Globalization.UnicodeCategory]::NonSpacingMark) { continue }
        if ($ch -match '[a-z0-9-]') { [void]$sb.Append($ch) }
    }
    return $sb.ToString().Trim('-')
}

function ConvertTo-OnbUpnAlias {
    <# First given name + last surname (Portuguese naming: "Ana Rita" "Sousa Ferreira" -> ana.ferreira). #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [string] $GivenName, [Parameter(Mandatory)] [string] $Surname)

    $first = ConvertTo-OnbAsciiName (($GivenName.Trim() -split '\s+')[0])
    $last = ConvertTo-OnbAsciiName (($Surname.Trim() -split '\s+')[-1])
    if (-not $first -or -not $last) { throw [OnbValidationException]::new("Can't build a sign-in name from '$GivenName' '$Surname'.") }
    $alias = "$first.$last"
    if ($alias.Length -gt 60) { $alias = $alias.Substring(0, 60).TrimEnd('.', '-') }
    return $alias
}

function Get-OnbUpnCandidates {
    <# alias@domain, alias2@domain ... alias9@domain. The provisioning service does not resolve UPN conflicts
       (Learn FAQ: "add the logic for unique UPN generation in your API client"), so we do. #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param([Parameter(Mandatory)] [string] $Alias, [Parameter(Mandatory)] [string] $Domain, [int] $Max = 9)

    $list = [System.Collections.Generic.List[string]]::new()
    $list.Add("$Alias@$Domain")
    for ($i = 2; $i -le $Max; $i++) { $list.Add("$Alias$i@$Domain") }
    return , $list.ToArray()
}

function Get-OnbEmployeeId {
    <# The list item ID becomes the employee ID (max 16 characters in Entra). It is the SCIM externalId, which the
       provisioning app matches to employeeId: same request, same account, however often we send it. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [int] $ItemId)
    if ($ItemId -le 0) { throw [OnbValidationException]::new("Invalid item ID $ItemId.") }
    return 'NH{0:D5}' -f $ItemId
}

function ConvertTo-OnbLocalDate {
    <# A SharePoint date-only value read through Graph is a UTC timestamp; turn it back into the calendar date of
       the site's time zone. #>
    [CmdletBinding()]
    [OutputType([datetime])]
    param([Parameter(Mandatory)] $Value, [Parameter(Mandatory)] [string] $TimeZoneId)

    $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById($TimeZoneId)
    return [System.TimeZoneInfo]::ConvertTime((ConvertTo-OnbUtc $Value), $tz).Date
}

function ConvertTo-OnbUtc {
    <# Graph JSON timestamps arrive as strings or, after ConvertFrom-Json, as DateTime (Kind Utc). Unspecified = UTC. #>
    [CmdletBinding()]
    [OutputType([datetimeoffset])]
    param([Parameter(Mandatory)] $Value)
    if ($Value -is [datetimeoffset]) { return $Value.ToUniversalTime() }
    if ($Value -is [datetime]) {
        $utc = if ($Value.Kind -eq [System.DateTimeKind]::Local) { $Value.ToUniversalTime() } else { [datetime]::SpecifyKind($Value, [System.DateTimeKind]::Utc) }
        return [datetimeoffset]::new($utc)
    }
    return [datetimeoffset]::Parse([string]$Value, [cultureinfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::AssumeUniversal).ToUniversalTime()
}

function ConvertTo-OnbHireDateTime {
    <# employeeHireDate = start date at StartHour local time, as UTC. Lifecycle Workflows evaluate in UTC and the
       TAP task uses the hire date as the TAP start time, so the time portion matters. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [datetime] $StartDate, [Parameter(Mandatory)] [string] $TimeZoneId, [int] $StartHour = 9)

    $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById($TimeZoneId)
    $local = [datetime]::SpecifyKind($StartDate.Date.AddHours($StartHour), [System.DateTimeKind]::Unspecified)
    $utc = [System.TimeZoneInfo]::ConvertTimeToUtc($local, $tz)
    return $utc.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [cultureinfo]::InvariantCulture)
}

function Test-OnbRequest {
    <# Returns a list of problems (empty = valid). The canvas app validates too; this is the server-side check. #>
    [CmdletBinding()]
    [OutputType([string[]])]
    param(
        [Parameter(Mandatory)] [hashtable] $Fields,
        [Parameter(Mandatory)] [string[]] $Departments,
        [Parameter(Mandatory)] [datetime] $Today
    )
    $problems = [System.Collections.Generic.List[string]]::new()
    foreach ($name in 'OnbGivenName', 'OnbSurname', 'OnbJobTitle', 'OnbManagerEmail', 'OnbDepartment', 'OnbStartDate') {
        if (-not $Fields.ContainsKey($name) -or [string]::IsNullOrWhiteSpace([string]$Fields[$name])) { $problems.Add("$name is required.") }
    }
    foreach ($name in 'OnbGivenName', 'OnbSurname') {
        if ($Fields.ContainsKey($name) -and ([string]$Fields[$name]).Length -gt 64) { $problems.Add("$name is longer than 64 characters.") }
    }
    if ($Fields['OnbManagerEmail'] -and [string]$Fields['OnbManagerEmail'] -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
        $problems.Add('OnbManagerEmail is not an e-mail address.')
    }
    if ($Fields['OnbDepartment'] -and $Departments -notcontains [string]$Fields['OnbDepartment']) {
        $problems.Add("Department '$($Fields['OnbDepartment'])' is not one of: $($Departments -join ', ').")
    }
    $usage = if ($Fields['OnbUsageLocation']) { [string]$Fields['OnbUsageLocation'] } else { 'PT' }
    if ($usage -cnotmatch '^[A-Z]{2}$') { $problems.Add("Usage location '$usage' must be a two-letter country code.") }
    if ($Fields['OnbStartDate'] -and $Fields['OnbStartDate'] -is [datetime] -and $Fields['OnbStartDate'].Date -lt $Today.Date) {
        $problems.Add('Start date is in the past: the new-hire workflows would never run for it.')
    }
    return , $problems.ToArray()
}

function New-OnbScimOperation {
    <# One SCIM bulk operation. Core + Enterprise schema, plus a custom namespace for HireDate and UsageLocation
       (they must be added to the provisioning app schema and mapped to employeeHireDate and usageLocation). #>
    [CmdletBinding()]
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)] [hashtable] $Fields,
        [Parameter(Mandatory)] [string] $EmployeeId,
        [Parameter(Mandatory)] [string] $UserPrincipalName,
        [Parameter(Mandatory)] [string] $ManagerEmployeeId,
        [Parameter(Mandatory)] [string] $HireDateUtc
    )
    $given = ([string]$Fields.OnbGivenName).Trim()
    $sur = ([string]$Fields.OnbSurname).Trim()
    $usage = if ($Fields['OnbUsageLocation']) { [string]$Fields['OnbUsageLocation'] } else { 'PT' }
    return [ordered]@{
        method = 'POST'
        bulkId = $EmployeeId
        path   = '/Users'
        data   = [ordered]@{
            schemas      = @('urn:ietf:params:scim:schemas:core:2.0:User', $script:ScimEnterpriseSchema, $script:ScimCustomSchema)
            externalId   = $EmployeeId
            userName     = $UserPrincipalName
            name         = [ordered]@{ givenName = $given; familyName = $sur }
            displayName  = "$given $sur"
            title        = ([string]$Fields.OnbJobTitle).Trim()
            userType     = 'Employee'
            active       = $false   # the account stays disabled until 'Onboard new hire employee' enables it on day one
            $script:ScimEnterpriseSchema = [ordered]@{
                employeeNumber = $EmployeeId
                department     = [string]$Fields.OnbDepartment
                manager        = [ordered]@{ value = $ManagerEmployeeId }   # the manager's externalId = their employeeId
            }
            $script:ScimCustomSchema = [ordered]@{ HireDate = $HireDateUtc; UsageLocation = $usage }
        }
    }
}

function New-OnbScimBulkRequest {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [object[]] $Operations)
    if ($Operations.Count -eq 0) { throw 'A bulk request needs at least one operation.' }
    if ($Operations.Count -gt 50) { throw "A bulk request can carry at most 50 operations (got $($Operations.Count))." }
    return [ordered]@{
        schemas      = @('urn:ietf:params:scim:api:messages:2.0:BulkRequest')
        Operations   = $Operations
        failOnErrors = $null
    }
}

function Get-OnbBusinessDay {
    <# Start date shifted by N working days (Mon-Fri). Offset 0 on a weekend moves forward to Monday. #>
    [CmdletBinding()]
    [OutputType([datetime])]
    param([Parameter(Mandatory)] [datetime] $Date, [Parameter(Mandatory)] [int] $Offset)

    $d = $Date.Date
    $isWeekend = { param($x) $x.DayOfWeek -in [DayOfWeek]::Saturday, [DayOfWeek]::Sunday }
    if ($Offset -eq 0) { while (& $isWeekend $d) { $d = $d.AddDays(1) }; return $d }
    $step = [math]::Sign($Offset)
    $left = [math]::Abs($Offset)
    while ($left -gt 0) {
        $d = $d.AddDays($step)
        if (-not (& $isWeekend $d)) { $left-- }
    }
    return $d
}

function New-OnbTaskPlan {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [int] $RequestId,
        [Parameter(Mandatory)] [datetime] $StartDate,
        [Parameter(Mandatory)] [string] $Department,
        [Parameter(Mandatory)] [string] $ManagerEmail,
        [Parameter(Mandatory)] [string] $NewHireUpn,
        [Parameter(Mandatory)] [pscustomobject] $Templates
    )
    $all = @($Templates.default)
    if ($Templates.byDepartment.PSObject.Properties[$Department]) { $all += @($Templates.byDepartment.$Department) }
    foreach ($t in $all) {
        $owner = switch ($t.owner) { 'Manager' { $ManagerEmail } 'New hire' { $NewHireUpn } default { $null } }
        [ordered]@{
            Title         = $t.title
            OnbRequestId  = $RequestId
            OnbTaskKey    = $t.key
            OnbOwnerRole  = $t.owner
            OnbOwnerEmail = $owner
            OnbDueDate    = (Get-OnbBusinessDay -Date $StartDate -Offset ([int]$t.offsetBusinessDays)).ToString('yyyy-MM-dd')
            OnbDone       = $false
        }
    }
}

#endregion

#region Microsoft Graph -----------------------------------------------------------------------------------------------

function Get-OnbAccessToken {
    <# Token for Microsoft Graph from the App Service / Functions managed identity endpoint (no SDK, no module:
       Flex Consumption doesn't support managed dependencies). Cached until five minutes before expiry. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([string] $ClientId = $env:AZURE_CLIENT_ID)

    if ($script:TokenCache -and $script:TokenCache.ExpiresOn -gt [datetimeoffset]::UtcNow.AddMinutes(5)) { return $script:TokenCache.Token }
    if (-not $env:IDENTITY_ENDPOINT -or -not $env:IDENTITY_HEADER) {
        throw 'No managed identity endpoint (IDENTITY_ENDPOINT / IDENTITY_HEADER). This code runs in Azure Functions.'
    }
    $uri = '{0}?resource={1}&api-version=2019-08-01' -f $env:IDENTITY_ENDPOINT, [uri]::EscapeDataString('https://graph.microsoft.com')
    if ($ClientId) { $uri += '&client_id=' + [uri]::EscapeDataString($ClientId) }   # user-assigned identity
    $r = Invoke-RestMethod -Method Get -Uri $uri -Headers @{ 'X-IDENTITY-HEADER' = $env:IDENTITY_HEADER }
    $script:TokenCache = @{ Token = $r.access_token; ExpiresOn = [datetimeoffset]::FromUnixTimeSeconds([long]$r.expires_on) }
    return $r.access_token
}

function Get-OnbRetryDelay {
    [CmdletBinding()]
    [OutputType([int])]
    param($Headers, [int] $Attempt)
    $retryAfter = if ($Headers -and $Headers['Retry-After']) { @($Headers['Retry-After'])[0] } else { $null }
    $seconds = 0
    if ($retryAfter -and [int]::TryParse([string]$retryAfter, [ref]$seconds)) { return [math]::Min([math]::Max($seconds, 1), 60) }
    return [math]::Min([int][math]::Pow(2, $Attempt), 30)
}

function Invoke-OnbGraph {
    <# Thin Graph client: bearer token, JSON in/out, If-Match, retries 429 and 5xx with Retry-After. Returns
       StatusCode, Body (parsed JSON or $null) and Headers; callers decide what a status means. #>
    [CmdletBinding()]
    param(
        [ValidateSet('GET', 'POST', 'PATCH')] [string] $Method = 'GET',
        [Parameter(Mandatory)] [string] $Path,
        $Body,
        [string] $ContentType = 'application/json',
        [string] $IfMatch,
        [int] $MaxAttempts = 4
    )
    $uri = if ($Path -match '^https://') { $Path } else { $script:GraphBase + $Path }
    if (-not $uri.StartsWith($script:GraphRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to send a Graph token to '$uri'."
    }
    $headers = @{ Authorization = 'Bearer ' + (Get-OnbAccessToken) }
    if ($IfMatch) { $headers['If-Match'] = $IfMatch }
    $json = if ($null -ne $Body) { ConvertTo-Json -InputObject $Body -Depth 20 -Compress } else { $null }

    for ($attempt = 1; ; $attempt++) {
        $params = @{ Method = $Method; Uri = $uri; Headers = $headers; SkipHttpErrorCheck = $true; UseBasicParsing = $true }
        if ($null -ne $json) { $params.Body = [System.Text.Encoding]::UTF8.GetBytes($json); $params.ContentType = "$ContentType; charset=utf-8" }
        $resp = Invoke-WebRequest @params
        $code = [int]$resp.StatusCode
        if (($code -eq 429 -or $code -ge 500) -and $attempt -lt $MaxAttempts) {
            Start-Sleep -Seconds (Get-OnbRetryDelay -Headers $resp.Headers -Attempt $attempt)
            continue
        }
        $parsed = $null
        if ($resp.Content -and ([string]$resp.Content).Trim().Length -gt 0) {
            try { $parsed = [string]$resp.Content | ConvertFrom-Json -Depth 30 } catch { $parsed = $null }
        }
        return [pscustomobject]@{ StatusCode = $code; Body = $parsed; Headers = $resp.Headers }
    }
}

function Get-OnbGraphError {
    param($Response)
    $msg = if ($Response.Body -and $Response.Body.PSObject.Properties['error'] -and $Response.Body.error.PSObject.Properties['message']) { $Response.Body.error.message } else { '(no error body)' }
    return "HTTP $($Response.StatusCode): $msg"
}

function ConvertTo-OnbHashtable {
    param($Object)
    $h = @{}
    if ($null -eq $Object) { return $h }
    foreach ($p in $Object.PSObject.Properties) { $h[$p.Name] = $p.Value }
    return $h
}

function Get-OnbListItems {
    <# Items of a list where ONE indexed column equals a value (Graph filters one indexed field at a time).
       Follows @odata.nextLink. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Config, [Parameter(Mandatory)] [string] $ListId,
          [Parameter(Mandatory)] [string] $Field, [Parameter(Mandatory)] $Value)

    $literal = if ($Value -is [int] -or $Value -is [long]) { "$Value" } else { "'" + ([string]$Value).Replace("'", "''") + "'" }
    $filter = [uri]::EscapeDataString("fields/$Field eq $literal")
    $path = "/sites/$($Config.SiteId)/lists/$ListId/items?`$expand=fields&`$filter=$filter&`$top=100"
    $items = [System.Collections.Generic.List[object]]::new()
    while ($path) {
        $r = Invoke-OnbGraph -Path $path
        if ($r.StatusCode -ne 200) { throw "Reading list $ListId failed: $(Get-OnbGraphError $r)" }
        foreach ($i in @($r.Body.value)) {
            $items.Add([pscustomobject]@{ Id = [int]$i.id; ETag = $i.eTag; Fields = (ConvertTo-OnbHashtable $i.fields) })
        }
        $path = if ($r.Body.PSObject.Properties['@odata.nextLink']) { $r.Body.'@odata.nextLink' } else { $null }
    }
    return $items.ToArray()   # unrolled: callers wrap in @() or foreach
}

function Set-OnbRequestFields {
    <# PATCH with If-Match: if HR edited the item since we read it, SharePoint answers 412 and we leave it for the
       next run instead of overwriting their change. Returns 'Updated' or 'Conflict'. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [hashtable] $Config, [Parameter(Mandatory)] [int] $ItemId,
          [string] $ETag, [Parameter(Mandatory)] [System.Collections.IDictionary] $Fields)

    $r = Invoke-OnbGraph -Method PATCH -Path "/sites/$($Config.SiteId)/lists/$($Config.RequestsListId)/items/$ItemId/fields" -Body $Fields -IfMatch $ETag
    if ($r.StatusCode -eq 412) { return 'Conflict' }
    if ($r.StatusCode -ne 200) { throw "Updating request $ItemId failed: $(Get-OnbGraphError $r)" }
    return 'Updated'
}

function Find-OnbUserByEmployeeId {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $EmployeeId)
    $filter = [uri]::EscapeDataString("employeeId eq '$($EmployeeId.Replace("'", "''"))'")
    $r = Invoke-OnbGraph -Path "/users?`$filter=$filter&`$select=id,userPrincipalName,employeeId,accountEnabled"
    if ($r.StatusCode -ne 200) { throw "Looking up employee $EmployeeId failed: $(Get-OnbGraphError $r)" }
    $found = @($r.Body.value)
    if ($found.Count -gt 1) { throw [OnbValidationException]::new("More than one account has employee ID $EmployeeId.") }
    if ($found.Count -eq 1) { return $found[0] }
    return $null
}

function Resolve-OnbUpn {
    <# First candidate that is free, or already belongs to this employee (a re-run). #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [string[]] $Candidates, [Parameter(Mandatory)] [string] $EmployeeId)

    foreach ($upn in $Candidates) {
        $filter = [uri]::EscapeDataString("userPrincipalName eq '$upn'")
        $r = Invoke-OnbGraph -Path "/users?`$filter=$filter&`$select=id,employeeId"
        if ($r.StatusCode -ne 200) { throw "Checking $upn failed: $(Get-OnbGraphError $r)" }
        $owner = @($r.Body.value)
        if ($owner.Count -eq 0) { return $upn }
        if ($owner[0].PSObject.Properties['employeeId'] -and $owner[0].employeeId -eq $EmployeeId) { return $upn }
    }
    throw [OnbValidationException]::new("All $($Candidates.Count) sign-in names for this person are taken.")
}

function Get-OnbManagerEmployeeId {
    <# The provisioning service resolves manager.value against the manager's externalId, i.e. employeeId in Entra.
       A manager without an employee ID would silently get no manager, and the TAP e-mail would have nowhere to go. #>
    [CmdletBinding()]
    [OutputType([string])]
    param([Parameter(Mandatory)] [string] $ManagerEmail)

    $r = Invoke-OnbGraph -Path "/users/$([uri]::EscapeDataString($ManagerEmail))?`$select=id,employeeId,accountEnabled"
    if ($r.StatusCode -eq 404) { throw [OnbValidationException]::new("Hiring manager $ManagerEmail was not found in Microsoft Entra.") }
    if ($r.StatusCode -ne 200) { throw "Looking up manager $ManagerEmail failed: $(Get-OnbGraphError $r)" }
    if (-not $r.Body.PSObject.Properties['employeeId'] -or [string]::IsNullOrWhiteSpace($r.Body.employeeId)) {
        throw [OnbValidationException]::new("Hiring manager $ManagerEmail has no employee ID; the provisioning service matches managers by employeeId.")
    }
    return [string]$r.Body.employeeId
}

function Send-OnbScimBulk {
    <# POST /servicePrincipals/{sp}/synchronization/jobs/{job}/bulkUpload with application/scim+json.
       202 = staged for the provisioning job; Location points at the provisioning logs for this job. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Config, [Parameter(Mandatory)] [System.Collections.IDictionary] $BulkRequest)

    $path = "/servicePrincipals/$($Config.ProvisioningServicePrincipalId)/synchronization/jobs/$($Config.ProvisioningJobId)/bulkUpload"
    $r = Invoke-OnbGraph -Method POST -Path $path -Body $BulkRequest -ContentType 'application/scim+json'
    $location = if ($r.Headers -and $r.Headers['Location']) { @($r.Headers['Location'])[0] } else { $null }
    return [pscustomobject]@{ Accepted = ($r.StatusCode -eq 202); StatusCode = $r.StatusCode; Location = $location; Error = $(if ($r.StatusCode -ne 202) { Get-OnbGraphError $r }) }
}

function Add-OnbTasks {
    <# Creates the checklist items that don't exist yet for this request (idempotent by OnbTaskKey). #>
    [CmdletBinding()]
    [OutputType([int])]
    param([Parameter(Mandatory)] [hashtable] $Config, [Parameter(Mandatory)] [int] $RequestId, [Parameter(Mandatory)] [object[]] $Plan)

    $existing = @(Get-OnbListItems -Config $Config -ListId $Config.TasksListId -Field 'OnbRequestId' -Value $RequestId) |
        ForEach-Object { $_.Fields['OnbTaskKey'] }
    $created = 0
    foreach ($task in $Plan) {
        if ($existing -contains $task.OnbTaskKey) { continue }
        $r = Invoke-OnbGraph -Method POST -Path "/sites/$($Config.SiteId)/lists/$($Config.TasksListId)/items" -Body @{ fields = $task }
        if ($r.StatusCode -ne 201) { throw "Creating task '$($task.OnbTaskKey)' for request $RequestId failed: $(Get-OnbGraphError $r)" }
        $created++
    }
    return $created
}

#endregion

#region Orchestration -------------------------------------------------------------------------------------------------

function Get-OnbConfigFromEnvironment {
    [CmdletBinding()]
    param([string] $TemplatesPath = (Join-Path $PSScriptRoot '..' '..' 'config' 'task-templates.json'))

    $required = [ordered]@{
        SiteId                         = 'Onboarding__SiteId'
        RequestsListId                 = 'Onboarding__RequestsListId'
        TasksListId                    = 'Onboarding__TasksListId'
        ProvisioningServicePrincipalId = 'Onboarding__ProvisioningServicePrincipalId'
        ProvisioningJobId              = 'Onboarding__ProvisioningJobId'
        UpnDomain                      = 'Onboarding__UpnDomain'
    }
    $config = @{}
    $missing = @()
    foreach ($k in $required.Keys) {
        $v = [Environment]::GetEnvironmentVariable($required[$k])
        if ([string]::IsNullOrWhiteSpace($v)) { $missing += $required[$k] } else { $config[$k] = $v.Trim() }
    }
    if ($missing) { throw "Missing app settings: $($missing -join ', ')" }
    $config.TimeZoneId = if ($env:Onboarding__TimeZone) { $env:Onboarding__TimeZone } else { 'Europe/Lisbon' }
    $config.StartHour = if ($env:Onboarding__StartHour) { [int]$env:Onboarding__StartHour } else { 9 }
    $config.SentTimeoutMinutes = if ($env:Onboarding__SentTimeoutMinutes) { [int]$env:Onboarding__SentTimeoutMinutes } else { 60 }
    $config.Departments = @('Sales', 'Finance', 'Operations', 'IT')
    $config.Templates = Get-Content -LiteralPath $TemplatesPath -Raw | ConvertFrom-Json
    return $config
}

function Invoke-OnbSync {
    <#
    .SYNOPSIS
      One pass: Approved -> (validate, resolve manager and UPN) -> one SCIM bulk request -> 'Sent to Entra';
      'Sent to Entra' -> (account exists?) -> tasks + 'Account created', or 'Failed' after the timeout.
      Returns one result object per item that changed (or was skipped because of a conflict).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [hashtable] $Config, [datetimeoffset] $Now = [datetimeoffset]::UtcNow)

    $results = [System.Collections.Generic.List[object]]::new()
    $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById($Config.TimeZoneId)
    $today = [System.TimeZoneInfo]::ConvertTime($Now, $tz).Date
    $nowText = $Now.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", [cultureinfo]::InvariantCulture)
    $record = {
        param($item, $to, $note, $outcome)
        $results.Add([pscustomobject]@{ ItemId = $item.Id; From = $item.Fields['OnbStatus']; To = $to; Outcome = $outcome; Note = $note })
    }

    # 1. Approved requests -> SCIM
    $ready = [System.Collections.Generic.List[object]]::new()
    foreach ($item in Get-OnbListItems -Config $Config -ListId $Config.RequestsListId -Field 'OnbStatus' -Value 'Approved') {
        $f = $item.Fields.Clone()
        if ($f['OnbStartDate']) { $f['OnbStartDate'] = ConvertTo-OnbLocalDate -Value $f['OnbStartDate'] -TimeZoneId $Config.TimeZoneId }
        try {
            $problems = Test-OnbRequest -Fields $f -Departments $Config.Departments -Today $today
            if ($problems.Count) { throw [OnbValidationException]::new($problems -join ' ') }
            $employeeId = Get-OnbEmployeeId -ItemId $item.Id
            $managerId = Get-OnbManagerEmployeeId -ManagerEmail ([string]$f.OnbManagerEmail).Trim()
            $existing = Find-OnbUserByEmployeeId -EmployeeId $employeeId
            $upn = if ($existing) { $existing.userPrincipalName } else {
                $alias = ConvertTo-OnbUpnAlias -GivenName $f.OnbGivenName -Surname $f.OnbSurname
                Resolve-OnbUpn -Candidates (Get-OnbUpnCandidates -Alias $alias -Domain $Config.UpnDomain) -EmployeeId $employeeId
            }
            $hire = ConvertTo-OnbHireDateTime -StartDate $f.OnbStartDate -TimeZoneId $Config.TimeZoneId -StartHour $Config.StartHour
            $op = New-OnbScimOperation -Fields $f -EmployeeId $employeeId -UserPrincipalName $upn -ManagerEmployeeId $managerId -HireDateUtc $hire
            $ready.Add([pscustomobject]@{ Item = $item; EmployeeId = $employeeId; Upn = $upn; Operation = $op })
        }
        catch [OnbValidationException] {
            $outcome = Set-OnbRequestFields -Config $Config -ItemId $item.Id -ETag $item.ETag -Fields ([ordered]@{ OnbStatus = 'Failed'; OnbMessage = $_.Exception.Message })
            & $record $item 'Failed' $_.Exception.Message $outcome
        }
    }

    for ($i = 0; $i -lt $ready.Count; $i += 50) {
        $chunk = $ready.GetRange($i, [math]::Min(50, $ready.Count - $i))
        $send = Send-OnbScimBulk -Config $Config -BulkRequest (New-OnbScimBulkRequest -Operations @($chunk | ForEach-Object Operation))
        if (-not $send.Accepted -and $send.StatusCode -notin 400, 403) {
            throw "bulkUpload failed, requests stay Approved for the next run: $($send.Error)"
        }
        foreach ($r in $chunk) {
            $fields = if ($send.Accepted) {
                [ordered]@{ OnbStatus = 'Sent to Entra'; OnbEmployeeId = $r.EmployeeId; OnbUpn = $r.Upn; OnbSentAt = $nowText
                            OnbMessage = "Sent to the provisioning service as $($r.EmployeeId); waiting for the account." }
            } else {
                [ordered]@{ OnbStatus = 'Failed'; OnbMessage = "The provisioning API refused the request: $($send.Error)" }
            }
            $outcome = Set-OnbRequestFields -Config $Config -ItemId $r.Item.Id -ETag $r.Item.ETag -Fields $fields
            & $record $r.Item $fields.OnbStatus $fields.OnbMessage $outcome
        }
    }

    # 2. Sent -> account exists?
    foreach ($item in Get-OnbListItems -Config $Config -ListId $Config.RequestsListId -Field 'OnbStatus' -Value 'Sent to Entra') {
        $f = $item.Fields
        $employeeId = if ($f['OnbEmployeeId']) { [string]$f['OnbEmployeeId'] } else { Get-OnbEmployeeId -ItemId $item.Id }
        $user = Find-OnbUserByEmployeeId -EmployeeId $employeeId
        if ($user) {
            $start = ConvertTo-OnbLocalDate -Value $f['OnbStartDate'] -TimeZoneId $Config.TimeZoneId
            $plan = @(New-OnbTaskPlan -RequestId $item.Id -StartDate $start -Department $f.OnbDepartment -ManagerEmail $f.OnbManagerEmail -NewHireUpn $user.userPrincipalName -Templates $Config.Templates)
            $created = Add-OnbTasks -Config $Config -RequestId $item.Id -Plan $plan
            $note = "Account $($user.userPrincipalName) created (disabled until day one). $created onboarding tasks added."
            $outcome = Set-OnbRequestFields -Config $Config -ItemId $item.Id -ETag $item.ETag -Fields ([ordered]@{
                OnbStatus = 'Account created'; OnbObjectId = $user.id; OnbUpn = $user.userPrincipalName; OnbMessage = $note })
            & $record $item 'Account created' $note $outcome
            continue
        }
        $sentAt = if ($f['OnbSentAt']) { ConvertTo-OnbUtc $f['OnbSentAt'] } else { $Now }
        if (($Now - $sentAt).TotalMinutes -ge $Config.SentTimeoutMinutes) {
            $note = "No account with employee ID $employeeId after $($Config.SentTimeoutMinutes) minutes. Check the provisioning logs of the API-driven provisioning app."
            $outcome = Set-OnbRequestFields -Config $Config -ItemId $item.Id -ETag $item.ETag -Fields ([ordered]@{ OnbStatus = 'Failed'; OnbMessage = $note })
            & $record $item 'Failed' $note $outcome
        }
    }
    return , $results.ToArray()
}

#endregion

Export-ModuleMember -Function ConvertTo-OnbAsciiName, ConvertTo-OnbUpnAlias, Get-OnbUpnCandidates, Get-OnbEmployeeId,
    ConvertTo-OnbLocalDate, ConvertTo-OnbUtc, ConvertTo-OnbHireDateTime, Test-OnbRequest, New-OnbScimOperation, New-OnbScimBulkRequest,
    Get-OnbBusinessDay, New-OnbTaskPlan, Get-OnbAccessToken, Get-OnbRetryDelay, Invoke-OnbGraph, Get-OnbListItems,
    Set-OnbRequestFields, Find-OnbUserByEmployeeId, Resolve-OnbUpn, Get-OnbManagerEmployeeId, Send-OnbScimBulk,
    Add-OnbTasks, Get-OnbConfigFromEnvironment, Invoke-OnbSync
