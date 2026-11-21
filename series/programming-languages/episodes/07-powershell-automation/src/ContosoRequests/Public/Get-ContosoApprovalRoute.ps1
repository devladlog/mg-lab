function Get-ContosoApprovalRoute {
    <#
    .SYNOPSIS
        Works out who has to approve each request: manager, then finance, then the board.
    .DESCRIPTION
        Normal = manager. High = manager + finance. Board = manager + finance + board.
        A department that is not in the approvers file is a non-terminating error for that
        request only.
    .EXAMPLE
        Import-ContosoRequest .\samples\requests.csv | Get-ContosoApprovalRoute -ApproverPath .\samples\approvers.json
    #>
    [CmdletBinding()]
    [OutputType('Contoso.ApprovalRoute')]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [ValidateScript({ $_.PSObject.TypeNames -contains 'Contoso.Request' },
            ErrorMessage = 'Pass Contoso.Request objects from Import-ContosoRequest.')]
        [psobject] $Request,

        [Parameter(Mandatory)]
        [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf }, ErrorMessage = 'Cannot find the approvers file "{0}".')]
        [string] $ApproverPath
    )

    begin {
        # A broken approvers file is the caller's problem, not one row's: let it stop the command.
        $directory = Get-Content -LiteralPath $ApproverPath -Raw | ConvertFrom-Json -ErrorAction Stop
    }

    process {
        $entry = $directory.departments.PSObject.Properties[$Request.Department]
        if (-not $entry) {
            $exception = [System.Collections.Generic.KeyNotFoundException]::new(
                "$($Request.Code): department '$($Request.Department)' is not in the approvers file.")
            $errorRecord = [System.Management.Automation.ErrorRecord]::new(
                $exception, 'ContosoRequest.UnknownDepartment',
                [System.Management.Automation.ErrorCategory]::ObjectNotFound, $Request)
            $PSCmdlet.WriteError($errorRecord)
            return
        }

        $approvers = [System.Collections.Generic.List[object]]::new()
        $approvers.Add([pscustomobject]@{ Role = 'Manager'; Name = $entry.Value.manager })
        if ($Request.Priority -in 'High', 'Board') {
            $approvers.Add([pscustomobject]@{ Role = 'Finance'; Name = $entry.Value.finance })
        }
        if ($Request.Priority -eq 'Board') {
            $approvers.Add([pscustomobject]@{ Role = 'Board'; Name = $directory.board })
        }

        [pscustomobject]@{
            PSTypeName = 'Contoso.ApprovalRoute'
            Request    = $Request
            Department = $entry.Name    # canonical spelling from the approvers file: 'it' becomes 'IT'
            Approvers  = $approvers.ToArray()
        }
    }
}
