# In-memory stand-in for the slice of Microsoft Graph that OnboardingSync calls. TESTS ONLY: the demo runs against
# the real tenant. It mimics the documented behaviour the code depends on:
#   - list items: $filter on one field, paging with @odata.nextLink, PATCH .../fields honouring If-Match (412)
#   - users: $filter on employeeId / userPrincipalName, GET /users/{upn-or-mail} (404 when unknown)
#   - bulkUpload: needs Content-Type application/scim+json (else 400), answers 202 + Location
#   - RunProvisioning(): what the provisioning job does with the staged operations: match externalId to employeeId,
#     create or update, resolve manager.value against employeeId, fail on a UPN that's already taken.

class FakeGraph {
    [string] $SiteId = 'contoso.sharepoint.com,00000000-0000-0000-0000-000000000001,00000000-0000-0000-0000-000000000002'
    [string] $RequestsListId = '00000000-0000-0000-0000-0000000000a1'
    [string] $TasksListId = '00000000-0000-0000-0000-0000000000a2'
    [string] $SpId = '00000000-0000-0000-0000-0000000000b1'
    [string] $JobId = 'API2AAD.00000000000000000000000000000000.00000000-0000-0000-0000-0000000000b1'
    [hashtable] $Lists = @{}
    [System.Collections.Generic.List[hashtable]] $Users = [System.Collections.Generic.List[hashtable]]::new()
    [System.Collections.Generic.List[object]] $Staged = [System.Collections.Generic.List[object]]::new()
    [System.Collections.Generic.List[string]] $ProvisioningLog = [System.Collections.Generic.List[string]]::new()
    [System.Collections.Generic.List[string]] $Calls = [System.Collections.Generic.List[string]]::new()
    [int] $BulkStatus = 202
    [int] $PageSize = 100
    [scriptblock] $BeforePatch = $null   # lets a test simulate an HR edit between read and write

    FakeGraph() {
        $this.Lists[$this.RequestsListId] = @{ Items = [System.Collections.Generic.List[hashtable]]::new(); NextId = 1 }
        $this.Lists[$this.TasksListId] = @{ Items = [System.Collections.Generic.List[hashtable]]::new(); NextId = 1 }
    }

    [hashtable] AddRequest([hashtable] $fields) {
        $list = $this.Lists[$this.RequestsListId]
        $item = @{ Id = $list.NextId; Version = 1; Fields = $fields.Clone() }
        $item.Fields['id'] = "$($list.NextId)"
        $list.NextId++
        $list.Items.Add($item)
        return $item
    }

    [hashtable] AddUser([hashtable] $user) {
        if (-not $user.ContainsKey('id')) { $user['id'] = [guid]::NewGuid().ToString() }
        $this.Users.Add($user)
        return $user
    }

    [hashtable] Request([int] $id) { return ($this.Lists[$this.RequestsListId].Items | Where-Object { $_.Id -eq $id } | Select-Object -First 1) }
    [object[]] Tasks([int] $requestId) { return @($this.Lists[$this.TasksListId].Items | Where-Object { $_.Fields.OnbRequestId -eq $requestId }) }
    [hashtable] UserByEmployeeId([string] $e) { return ($this.Users | Where-Object { $_.employeeId -eq $e } | Select-Object -First 1) }

    hidden [string] ETag([hashtable] $item) { return '"00000000-0000-0000-0000-{0:D12},{1}"' -f $item.Id, $item.Version }

    hidden [object] Respond([int] $code, $body, [hashtable] $headers) {
        $parsed = if ($null -ne $body) { $body | ConvertTo-Json -Depth 20 | ConvertFrom-Json -Depth 20 } else { $null }
        return [pscustomobject]@{ StatusCode = $code; Body = $parsed; Headers = $headers }
    }

    hidden [object] Error([int] $code, [string] $message) { return $this.Respond($code, @{ error = @{ code = "$code"; message = $message } }, @{}) }

    hidden [hashtable] ParseQuery([string] $query) {
        $q = @{}
        foreach ($pair in $query.Split('&', [System.StringSplitOptions]::RemoveEmptyEntries)) {
            $kv = $pair.Split('=', 2)
            $q[[uri]::UnescapeDataString($kv[0])] = if ($kv.Count -gt 1) { [uri]::UnescapeDataString($kv[1]) } else { '' }
        }
        return $q
    }

    # "fields/OnbStatus eq 'Approved'" | "employeeId eq 'NH00001'" | "fields/OnbRequestId eq 3"
    hidden [object[]] ParseEq([string] $filter) {
        if ($filter -notmatch "^(?<f>[\w/]+) eq (?:'(?<s>(?:[^']|'')*)'|(?<n>\d+))$") { throw "FakeGraph can't parse filter: $filter" }
        $value = if ($Matches.ContainsKey('n') -and $Matches['n']) { [int]$Matches['n'] } else { $Matches['s'].Replace("''", "'") }
        return @($Matches['f'], $value)
    }

    [object] Invoke([string] $method, [string] $path, $body, [string] $ifMatch, [string] $contentType) {
        $this.Calls.Add("$method $path")
        if ($path.StartsWith('https://graph.microsoft.com/v1.0')) { $path = $path.Substring('https://graph.microsoft.com/v1.0'.Length) }
        $pathOnly, $query = $path.Split('?', 2)
        $q = if ($query) { $this.ParseQuery($query) } else { @{} }
        $payload = if ($null -ne $body) { $body | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable -Depth 20 -DateKind String } else { $null }
        $siteEsc = [regex]::Escape($this.SiteId)

        # list items
        if ($pathOnly -match "^/sites/$siteEsc/lists/(?<list>[^/]+)/items$") {
            $list = $this.Lists[$Matches['list']]
            if (-not $list) { return $this.Error(404, 'List not found') }
            if ($method -eq 'GET') {
                $field, $value = $this.ParseEq($q['$filter'])
                $name = $field -replace '^fields/', ''
                $all = @($list.Items | Where-Object { $_.Fields.ContainsKey($name) -and $_.Fields[$name] -eq $value })
                $skip = if ($q.ContainsKey('$skiptoken')) { [int]$q['$skiptoken'] } else { 0 }
                $page = @($all | Select-Object -Skip $skip -First $this.PageSize)
                $result = [ordered]@{ value = @($page | ForEach-Object { @{ id = "$($_.Id)"; eTag = $this.ETag($_); fields = $_.Fields } }) }
                if ($skip + $this.PageSize -lt $all.Count) {
                    $baseQuery = ($query.Split('&') | Where-Object { $_ -notlike '$skiptoken=*' }) -join '&'
                    $result['@odata.nextLink'] = "https://graph.microsoft.com/v1.0$pathOnly`?$baseQuery&`$skiptoken=$($skip + $this.PageSize)"
                }
                return $this.Respond(200, $result, @{})
            }
            if ($method -eq 'POST') {
                $item = @{ Id = $list.NextId; Version = 1; Fields = $payload.fields }
                $item.Fields['id'] = "$($list.NextId)"
                $list.NextId++
                $list.Items.Add($item)
                return $this.Respond(201, @{ id = "$($item.Id)"; fields = $item.Fields }, @{})
            }
        }
        if ($method -eq 'PATCH' -and $pathOnly -match "^/sites/$siteEsc/lists/(?<list>[^/]+)/items/(?<id>\d+)/fields$") {
            $list = $this.Lists[$Matches['list']]
            $item = $list.Items | Where-Object { $_.Id -eq [int]$Matches['id'] } | Select-Object -First 1
            if (-not $item) { return $this.Error(404, 'Item not found') }
            if ($this.BeforePatch) { & $this.BeforePatch $item }
            if ($ifMatch -and $ifMatch -ne $this.ETag($item)) { return $this.Error(412, 'The eTag value does not match the current item.') }
            foreach ($k in $payload.Keys) { $item.Fields[$k] = $payload[$k] }
            $item.Version++
            return $this.Respond(200, $item.Fields, @{})
        }

        # users
        if ($method -eq 'GET' -and $pathOnly -eq '/users') {
            $field, $value = $this.ParseEq($q['$filter'])
            $found = @($this.Users | Where-Object { $_.ContainsKey($field) -and [string]::Equals([string]$_[$field], [string]$value, [System.StringComparison]::OrdinalIgnoreCase) })
            return $this.Respond(200, @{ value = @($found | ForEach-Object { @{ id = $_.id; userPrincipalName = $_.userPrincipalName; employeeId = $_['employeeId']; accountEnabled = $_['accountEnabled'] } }) }, @{})
        }
        if ($method -eq 'GET' -and $pathOnly -match '^/users/(?<key>[^/]+)$') {
            $key = [uri]::UnescapeDataString($Matches['key'])
            $u = $this.Users | Where-Object { $_.userPrincipalName -eq $key -or $_['mail'] -eq $key } | Select-Object -First 1
            if (-not $u) { return $this.Error(404, "Resource '$key' does not exist.") }
            return $this.Respond(200, @{ id = $u.id; employeeId = $u['employeeId']; accountEnabled = $u['accountEnabled'] }, @{})
        }

        # provisioning
        if ($method -eq 'POST' -and $pathOnly -eq "/servicePrincipals/$($this.SpId)/synchronization/jobs/$($this.JobId)/bulkUpload") {
            if ($contentType -notlike 'application/scim+json*') { return $this.Error(400, 'Content-Type must be application/scim+json.') }
            if ($this.BulkStatus -ne 202) { return $this.Error($this.BulkStatus, 'Simulated failure.') }
            if (@($payload.Operations).Count -gt 50) { return $this.Error(400, 'Too many operations.') }
            foreach ($op in $payload.Operations) { $this.Staged.Add($op) }
            return $this.Respond(202, $null, @{ Location = @("https://graph.microsoft.com/v1.0/auditLogs/provisioning/?`$filter=jobid%20eq%20'$($this.JobId)'") })
        }
        return $this.Error(400, "FakeGraph has no route for $method $pathOnly")
    }

    [void] RunProvisioning() {
        $ent = 'urn:ietf:params:scim:schemas:extension:enterprise:2.0:User'
        $custom = 'urn:ietf:params:scim:schemas:extension:contoso:1.0:User'
        foreach ($op in $this.Staged) {
            $d = $op.data
            $managerId = $null
            $mgr = $this.UserByEmployeeId([string]$d[$ent].manager.value)
            if ($mgr) { $managerId = $mgr.id }
            $existing = $this.UserByEmployeeId([string]$d.externalId)
            $props = @{ displayName = $d.displayName; department = $d[$ent].department; jobTitle = $d.title; accountEnabled = [bool]$d.active
                        employeeHireDate = $d[$custom].HireDate; usageLocation = $d[$custom].UsageLocation; managerId = $managerId }
            if ($existing) {
                foreach ($k in $props.Keys) { $existing[$k] = $props[$k] }
                $this.ProvisioningLog.Add("Update $($d.externalId): success")
                continue
            }
            if ($this.Users | Where-Object { $_.userPrincipalName -eq $d.userName }) {
                $this.ProvisioningLog.Add("Create $($d.externalId): failure, userPrincipalName $($d.userName) already exists")
                continue
            }
            $props.userPrincipalName = $d.userName
            $props.employeeId = $d.externalId
            $this.AddUser($props) | Out-Null
            $this.ProvisioningLog.Add("Create $($d.externalId): success")
        }
        $this.Staged.Clear()
    }
}
