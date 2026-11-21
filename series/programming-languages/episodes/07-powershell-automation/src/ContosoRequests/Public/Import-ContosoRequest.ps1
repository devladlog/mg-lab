function Import-ContosoRequest {
    <#
    .SYNOPSIS
        Reads project requests from a CSV file and returns typed Contoso.Request objects.
    .DESCRIPTION
        Valid rows go to the pipeline as objects. A bad row becomes a non-terminating error
        (with the row as TargetObject) and the next row is still processed. Use -ErrorVariable
        to collect the rejected rows, or -ErrorAction Stop to stop at the first one.
    .EXAMPLE
        Import-ContosoRequest .\samples\requests.csv -ErrorVariable rejected -ErrorAction SilentlyContinue
    #>
    [CmdletBinding()]
    [OutputType('Contoso.Request')]
    param(
        [Parameter(Mandatory, Position = 0, ValueFromPipeline, ValueFromPipelineByPropertyName)]
        [Alias('PSPath', 'FullName')]
        [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf }, ErrorMessage = 'Cannot find the CSV file "{0}".')]
        [string[]] $Path
    )

    process {
        foreach ($file in $Path) {
            $row = 1    # the header is row 1
            foreach ($record in Import-Csv -LiteralPath $file) {
                $row++
                $result = ConvertTo-ContosoRequest -Record $record
                if ($result.PSObject.TypeNames -contains 'Contoso.RecordProblem') {
                    $exception = [System.IO.InvalidDataException]::new($result.Message)
                    $errorRecord = [System.Management.Automation.ErrorRecord]::new(
                        $exception,
                        $result.ErrorId,
                        [System.Management.Automation.ErrorCategory]::InvalidData,
                        $record)
                    $errorRecord.ErrorDetails = "$(Split-Path -Leaf $file) row ${row}: $($result.Message)"
                    $PSCmdlet.WriteError($errorRecord)
                    continue
                }
                $result
            }
        }
    }
}
