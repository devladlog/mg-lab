function Export-ContosoApprovalPack {
    <#
    .SYNOPSIS
        Writes one JSON approval pack per request: <Destination>\<Department>\<Code>.json.
    .DESCRIPTION
        Supports -WhatIf and -Confirm. Never overwrites an existing pack unless -Force is used,
        so running it twice is safe. Use -PassThru to get a Contoso.ApprovalPack object per file.
    .EXAMPLE
        ... | Export-ContosoApprovalPack -Destination .\out -WhatIf
    #>
    [CmdletBinding(SupportsShouldProcess)]
    [OutputType('Contoso.ApprovalPack')]
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [ValidateScript({ $_.PSObject.TypeNames -contains 'Contoso.ApprovalRoute' },
            ErrorMessage = 'Pass Contoso.ApprovalRoute objects from Get-ContosoApprovalRoute.')]
        [psobject] $Route,

        [Parameter(Mandatory)]
        [string] $Destination,

        [switch] $Force,

        [switch] $PassThru
    )

    process {
        $request = $Route.Request
        $folder = Join-Path -Path $Destination -ChildPath $Route.Department
        $file = Join-Path -Path $folder -ChildPath "$($request.Code).json"

        if ((Test-Path -LiteralPath $file) -and -not $Force) {
            $exception = [System.IO.IOException]::new("$file already exists. Use -Force to overwrite it.")
            $errorRecord = [System.Management.Automation.ErrorRecord]::new(
                $exception, 'ContosoPack.AlreadyExists',
                [System.Management.Automation.ErrorCategory]::ResourceExists, $file)
            $PSCmdlet.WriteError($errorRecord)
            return
        }

        if ($PSCmdlet.ShouldProcess($file, 'Write approval pack')) {
            $pack = [ordered]@{
                request = [ordered]@{
                    code       = $request.Code
                    title      = $request.Title
                    department = $Route.Department
                    budget     = $request.Budget
                    submitted  = $request.Submitted.ToString('yyyy-MM-dd')
                }
                route   = [ordered]@{
                    priority  = $request.Priority
                    approvers = @($Route.Approvers | ForEach-Object { [ordered]@{ role = $_.Role; name = $_.Name } })
                }
            }

            $null = New-Item -ItemType Directory -Path $folder -Force
            # Default depth is 2: it would flatten the approver objects into the text "System.Collections..."
            $pack | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $file -Encoding utf8NoBOM

            if ($PassThru) {
                [pscustomobject]@{
                    PSTypeName = 'Contoso.ApprovalPack'
                    Code       = $request.Code
                    Priority   = $request.Priority
                    Approvers  = ($Route.Approvers.Name -join ', ')
                    Path       = $file
                }
            }
        }
    }
}
