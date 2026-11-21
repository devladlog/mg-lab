<#
.SYNOPSIS
  Exports Copilot interaction audit records (Operation CopilotInteraction) to CSV for copilot_chat_audit.
.DESCRIPTION
  Wraps Search-UnifiedAuditLog (Exchange Online PowerShell): pages with SessionId + SessionCommand ReturnLargeSet until
  the cmdlet returns nothing (Learn: up to 50,000 records per session, unsorted).
  Needs the tenant. Connect first, as an account with the Audit Logs or View-Only Audit Logs role in Exchange Online:
      Connect-ExchangeOnline -UserPrincipalName <admin UPN>
  Read-only. Microsoft recommends the Office 365 Management Activity API instead of this cmdlet for programmatic,
  recurring downloads; this script is for ad-hoc admin checks and the lab.
.EXAMPLE
  ./Export-CopilotInteractions.ps1 -StartDate (Get-Date).AddDays(-1) -OutFile $HOME/copilot-interactions.csv
  python -m copilot_chat_audit $HOME/copilot-interactions.csv
#>
[CmdletBinding()]
param(
    [datetime]$StartDate = (Get-Date).ToUniversalTime().AddDays(-7),
    [datetime]$EndDate = (Get-Date).ToUniversalTime(),
    [string[]]$UserIds,
    [string]$OutFile = './copilot-interactions.csv',
    [ValidateRange(1, 5000)][int]$PageSize = 5000,
    [ValidateRange(1, 50000)][int]$MaxRecords = 50000
)

function Get-CopilotInteractionRecords {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][datetime]$StartDate,
        [Parameter(Mandatory)][datetime]$EndDate,
        [string[]]$UserIds,
        [ValidateRange(1, 5000)][int]$PageSize = 5000,
        [ValidateRange(1, 50000)][int]$MaxRecords = 50000,
        [string]$SessionId = [guid]::NewGuid().ToString()
    )
    $all = New-Object System.Collections.Generic.List[object]
    do {
        $query = @{
            StartDate      = $StartDate
            EndDate        = $EndDate
            Operations     = 'CopilotInteraction'
            SessionId      = $SessionId
            SessionCommand = 'ReturnLargeSet'
            ResultSize     = $PageSize
        }
        if ($UserIds) { $query.UserIds = $UserIds }
        $page = @(Search-UnifiedAuditLog @query)
        if ($page.Count -gt 0) { $all.AddRange($page) }
    } while ($page.Count -gt 0 -and $all.Count -lt $MaxRecords)
    , $all.ToArray()
}

# Run the export only when executed, not when dot-sourced by the tests.
if ($MyInvocation.InvocationName -ne '.') {
    $ErrorActionPreference = 'Stop'
    if (-not (Get-Command Search-UnifiedAuditLog -ErrorAction SilentlyContinue)) {
        throw 'Search-UnifiedAuditLog not found. Run Connect-ExchangeOnline first (module ExchangeOnlineManagement).'
    }
    $records = Get-CopilotInteractionRecords -StartDate $StartDate -EndDate $EndDate -UserIds $UserIds `
        -PageSize $PageSize -MaxRecords $MaxRecords
    $records |
        Select-Object CreationDate, UserIds, Operations, RecordType, AuditData |
        Export-Csv -LiteralPath $OutFile -NoTypeInformation -Encoding utf8
    Write-Host ("{0} CopilotInteraction record(s) written to {1}" -f $records.Count, $OutFile)
    if ($records.Count -ge $MaxRecords) {
        Write-Warning "Reached $MaxRecords records: split the date range and run again, the rest was not exported."
    }
}
