function Get-ContosoPriority {
    <#
    .SYNOPSIS
        Maps a budget to the series approval priority (same rule as episode 6).
    .DESCRIPTION
        High starts AT 50,000 (>=), Board starts AT 250,000. Everything below is Normal.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [decimal] $Budget
    )

    if ($Budget -ge 250000) { return 'Board' }
    if ($Budget -ge 50000) { return 'High' }
    'Normal'
}
