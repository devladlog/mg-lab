#Requires -Version 7.2
<#
.SYNOPSIS
    Test RLS in the Power BI service: run one DAX query per user with impersonatedUserName and compare the result
    with the expected matrix (reference/expected/rls_matrix.csv).

.DESCRIPTION
    Uses Datasets - Execute Queries In Group (POST groups/{groupId}/datasets/{datasetId}/executeQueries) through
    Invoke-PowerBIRestMethod from the MicrosoftPowerBIMgmt module. The caller signs in first with
    Connect-PowerBIServiceAccount. Requirements (Learn): tenant setting "Dataset Execute Queries REST API" enabled,
    the caller has Read and Build on the semantic model, at most 120 queries per minute per user, and service
    principals aren't supported for semantic models with RLS: run it as a user.
#>

Set-StrictMode -Version Latest

$script:RlsQuery = @'
EVALUATE
ROW(
    "Who", [Who Am I],
    "Stores", [Visible Stores],
    "Customers", [Visible Customers],
    "Sales", [Sales Amount],
    "Orders", [Orders]
)
'@

function Get-RlsQuery { $script:RlsQuery }

function New-RlsQueryBody {
    <# The executeQueries request body for one user (JSON). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $UserPrincipalName)
    @{
        queries              = @(@{ query = $script:RlsQuery })
        serializerSettings   = @{ includeNulls = $true }
        impersonatedUserName = $UserPrincipalName
    } | ConvertTo-Json -Depth 5 -Compress
}

function ConvertFrom-RlsResponse {
    <# Turns the executeQueries JSON into one object; a query error becomes an exception. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string] $Json)
    $r = $Json | ConvertFrom-Json -AsHashtable
    foreach ($e in @($r['error'], $r['results']?[0]?['error'], $r['results']?[0]?['tables']?[0]?['error'])) {
        if ($e) { throw "executeQueries failed: $($e['code']) $($e['message'])" }
    }
    $rows = @($r['results'][0]['tables'][0]['rows'])
    if ($rows.Count -ne 1) { throw "expected 1 row, got $($rows.Count)" }
    $row = $rows[0]
    # Columns created in the query come back in square brackets: [Stores]. A BLANK measure is null.
    [pscustomobject]@{
        Who       = [string]$row['[Who]']
        Stores    = [int]($row['[Stores]'] ?? 0)
        Customers = [int]($row['[Customers]'] ?? 0)
        Sales     = [decimal]($row['[Sales]'] ?? 0)
        Orders    = [int]($row['[Orders]'] ?? 0)
    }
}

function Invoke-RlsQuery {
    <# Runs the RLS query as one user. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $DatasetId,
        [Parameter(Mandatory)][string] $UserPrincipalName
    )
    $json = Invoke-PowerBIRestMethod -Method Post `
        -Url "groups/$WorkspaceId/datasets/$DatasetId/executeQueries" `
        -Body (New-RlsQueryBody -UserPrincipalName $UserPrincipalName)
    ConvertFrom-RlsResponse -Json $json
}

function Compare-RlsResult {
    <# One expected row vs one actual result: PASS or FAIL with the reasons. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Expected,
        [Parameter(Mandatory)] $Actual,
        [Parameter(Mandatory)][string] $UserPrincipalName
    )
    $problems = [System.Collections.Generic.List[string]]::new()
    if ($Actual.Who -and $Actual.Who -ne $UserPrincipalName) { $problems.Add("Who Am I returned another identity") }
    if ($Actual.Stores -ne [int]$Expected.'Visible Stores') { $problems.Add("stores $($Actual.Stores), expected $($Expected.'Visible Stores')") }
    if ($Actual.Customers -ne [int]$Expected.'Visible Customers') { $problems.Add("customers $($Actual.Customers), expected $($Expected.'Visible Customers')") }
    if ([math]::Abs($Actual.Sales - [decimal]$Expected.'Sales Amount') -gt 0.005) { $problems.Add("sales $($Actual.Sales), expected $($Expected.'Sales Amount')") }
    if ($Actual.Orders -ne [int]$Expected.Orders) { $problems.Add("orders $($Actual.Orders), expected $($Expected.Orders)") }
    [pscustomobject]@{
        User      = $Expected.UserAlias          # the alias only: the tenant domain never reaches the console
        Roles     = $Expected.Roles
        Stores    = $Actual.Stores
        Customers = $Actual.Customers
        Sales     = $Actual.Sales.ToString('N2', [cultureinfo]::InvariantCulture)
        Result    = if ($problems.Count) { 'FAIL' } else { 'PASS' }
        Details   = $problems -join '; '
    }
}

function Test-RlsMatrix {
    <#
    .SYNOPSIS
        Runs the query for every user marked Service = yes in the matrix and returns one PASS/FAIL row per user.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string] $WorkspaceId,
        [Parameter(Mandatory)][string] $DatasetId,
        [Parameter(Mandatory)][string] $UpnDomain,
        [Parameter(Mandatory)][string] $ExpectedPath
    )
    $rows = Import-Csv -LiteralPath $ExpectedPath | Where-Object Service -eq 'yes'
    foreach ($row in $rows) {
        $upn = "$($row.UserAlias)@$UpnDomain".ToLowerInvariant()
        try {
            $actual = Invoke-RlsQuery -WorkspaceId $WorkspaceId -DatasetId $DatasetId -UserPrincipalName $upn
            Compare-RlsResult -Expected $row -Actual $actual -UserPrincipalName $upn
        }
        catch {
            [pscustomobject]@{ User = $row.UserAlias; Roles = $row.Roles; Stores = $null; Customers = $null
                               Sales = $null; Result = 'FAIL'; Details = $_.Exception.Message }
        }
    }
}

Export-ModuleMember -Function Get-RlsQuery, New-RlsQueryBody, ConvertFrom-RlsResponse, Invoke-RlsQuery, Compare-RlsResult, Test-RlsMatrix
