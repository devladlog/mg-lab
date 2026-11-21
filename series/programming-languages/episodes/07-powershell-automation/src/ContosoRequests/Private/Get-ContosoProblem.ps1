function Get-ContosoProblem {
    [CmdletBinding()]
    [OutputType('Contoso.RecordProblem')]
    param(
        [Parameter(Mandatory, Position = 0)] [string] $Id,
        [Parameter(Mandatory, Position = 1)] [string] $Message
    )

    [pscustomobject]@{ PSTypeName = 'Contoso.RecordProblem'; ErrorId = "ContosoRequest.$Id"; Message = $Message }
}
