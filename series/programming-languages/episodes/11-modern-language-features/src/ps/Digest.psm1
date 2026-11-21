# Contoso request digest, PowerShell 7.6 edition (classes, enums, ?? and ?. operators, ternary).
# Same input and output as the TypeScript, C# and Python versions: see expected/digest.txt.
#Requires -Version 7.4

Set-StrictMode -Version Latest

$script:HighPriorityCents = 5000000   # 50,000.00 EUR
$script:BoardCents = 25000000         # 250,000.00 EUR
$script:BatchSize = 4

enum Route {
    TeamLead
    Finance
    Board
}

class Request {
    [string] $Code
    [string] $Title
    [string] $Department
    [long]   $Cents

    Request([string] $code, [string] $title, [string] $department, [long] $cents) {
        $this.Code = $code
        $this.Title = $title
        $this.Department = $department
        $this.Cents = $cents
    }
}

function Get-RouteFor {
    [OutputType([Route])]
    param([Parameter(Mandatory)][long] $Cents)
    # Ternary operator (PowerShell 7): condition ? if-true : if-false
    return $Cents -ge $script:BoardCents ? [Route]::Board : ($Cents -ge $script:HighPriorityCents ? [Route]::Finance : [Route]::TeamLead)
}

function ConvertTo-Cents {
    [OutputType([long])]
    param([Parameter(Mandatory)][decimal] $Budget)
    # [decimal] keeps 49999.99 exact. Casting a double rounds in PowerShell, but never rely on that.
    return [long][Math]::Round($Budget * 100, 0, [MidpointRounding]::ToEven)
}

function Format-Money {
    [OutputType([string])]
    param([Parameter(Mandatory)][long] $Cents)
    return ($Cents / 100d).ToString('N2', [cultureinfo]::InvariantCulture)
}

function Read-DigestRequest {
    <#
    .SYNOPSIS
        Reads the JSON array of requests. Missing or mistyped fields are errors, not silent $null.
    #>
    [OutputType([pscustomobject[]])]
    param([Parameter(Mandatory)][string] $Path)

    $items = @(Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -NoEnumerate)
    $index = 0
    foreach ($item in $items[0]) {
        foreach ($name in 'code', 'title', 'department', 'budget', 'requestedBy') {
            # Under Set-StrictMode, $item.$name throws for a missing property: look it up instead.
            $property = $item.PSObject.Properties[$name]
            if ($null -eq ${property}?.Value) { throw "element ${index}: missing '$name'" }
        }
        [pscustomobject]@{
            Code       = [string] $item.code
            Title      = [string] $item.title
            Department = [string] $item.department
            Budget     = [decimal] $item.budget
        }
        $index++
    }
}

function New-Digest {
    [OutputType([pscustomobject])]
    param([Parameter(Mandatory)][AllowEmptyCollection()][pscustomobject[]] $Raw)

    $accepted = [System.Collections.Generic.List[Request]]::new()
    $rejected = [System.Collections.Generic.List[pscustomobject]]::new()
    foreach ($r in $Raw) {
        if ($r.Budget -le 0) {
            $rejected.Add([pscustomobject]@{ Code = $r.Code; Reason = 'budget must be greater than zero' })
        }
        else {
            $accepted.Add([Request]::new($r.Code, $r.Title, $r.Department.Trim().ToUpperInvariant(), (ConvertTo-Cents $r.Budget)))
        }
    }

    # Group-Object -AsHashTable would sort nothing for us; keep every route, even empty ones.
    $byRoute = $accepted | Group-Object -Property { Get-RouteFor $_.Cents } -AsHashTable -AsString
    $routes = [ordered]@{}
    foreach ($route in [Route].GetEnumValues()) {
        # ?[] and ?. are null-conditional (PowerShell 7.1+); @($null).Count would be 1, not 0.
        $group = ${byRoute}?[[string] $route]
        $routes[[string] $route] = ${group}?.Count ?? 0
    }

    $departments = $accepted |
        Group-Object -Property Department |
        ForEach-Object {
            [pscustomobject]@{
                Department = $_.Name
                Count      = $_.Count
                Cents      = [long] ($_.Group | Measure-Object -Property Cents -Sum).Sum
            }
        } |
        Sort-Object @{ Expression = 'Cents'; Descending = $true }, @{ Expression = 'Department'; Ascending = $true }

    $largest = $accepted |
        Sort-Object @{ Expression = 'Cents'; Descending = $true }, @{ Expression = 'Code'; Ascending = $true } |
        Select-Object -First 3

    $batches = [System.Collections.Generic.List[string[]]]::new()
    for ($i = 0; $i -lt $accepted.Count; $i += $script:BatchSize) {
        $last = [Math]::Min($i + $script:BatchSize, $accepted.Count) - 1
        $batches.Add([string[]] $accepted[$i..$last].Code)
    }

    [pscustomobject]@{
        Accepted     = $accepted
        Rejected     = $rejected
        TotalCents   = [long] ($accepted | Measure-Object -Property Cents -Sum).Sum
        HighPriority = @($accepted | Where-Object Cents -ge $script:HighPriorityCents).Count
        Routes       = $routes
        Departments  = @($departments)
        Largest      = @($largest)
        Batches      = $batches
    }
}

function Format-Digest {
    [OutputType([string])]
    param([Parameter(Mandatory)][pscustomobject] $Digest)

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('Contoso request digest')
    $lines.Add("accepted $($Digest.Accepted.Count), rejected $($Digest.Rejected.Count), total $(Format-Money $Digest.TotalCents) EUR, high priority $($Digest.HighPriority)")
    $lines.Add('rejected:')
    foreach ($r in $Digest.Rejected) { $lines.Add("  $($r.Code)  $($r.Reason)") }
    $lines.Add('by route:')
    foreach ($key in $Digest.Routes.Keys) { $lines.Add(('  {0,-9}{1,2}' -f $key, $Digest.Routes[$key])) }
    $lines.Add('by department:')
    foreach ($d in $Digest.Departments) { $lines.Add(('  {0,-6}{1,2}  {2,13} EUR' -f $d.Department, $d.Count, (Format-Money $d.Cents))) }
    $lines.Add('largest three:')
    $n = 1
    foreach ($r in $Digest.Largest) { $lines.Add("  ${n}. $($r.Code)  $($r.Title)  $(Format-Money $r.Cents) EUR"); $n++ }
    $lines.Add("review batches of ${script:BatchSize}:")
    $n = 1
    foreach ($b in $Digest.Batches) { $lines.Add("  ${n}: $($b -join ', ')"); $n++ }
    return ($lines -join "`n") + "`n"
}

function Invoke-Digest {
    [OutputType([string])]
    param([Parameter(Mandatory)][string] $Path)
    return Format-Digest (New-Digest (Read-DigestRequest -Path $Path))
}

Export-ModuleMember -Function Get-RouteFor, ConvertTo-Cents, Format-Money, Read-DigestRequest, New-Digest, Format-Digest, Invoke-Digest
