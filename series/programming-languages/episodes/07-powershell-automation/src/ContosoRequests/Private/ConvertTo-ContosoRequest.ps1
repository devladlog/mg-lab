function ConvertTo-ContosoRequest {
    <#
    .SYNOPSIS
        Validates one CSV record: returns a typed request object, or a problem description.
    .DESCRIPTION
        Never throws. A bad record comes back as a Contoso.RecordProblem (ErrorId + Message), and the
        public function writes it as a NON-terminating error, so one bad row does not stop the others.
        (Throwing and catching inside a helper also leaks every caught exception into the caller's
        -ErrorVariable: we saw 6 entries per bad row before we changed this.)
    #>
    [CmdletBinding()]
    [OutputType('Contoso.Request', 'Contoso.RecordProblem')]
    param(
        [Parameter(Mandatory)]
        [psobject] $Record
    )

    $invariant = [System.Globalization.CultureInfo]::InvariantCulture

    $code = "$($Record.code)".Trim()
    if ($code -notmatch '^PR-\d{4}-\d{4}$') {
        return Get-ContosoProblem 'InvalidCode' "Code '$code' does not look like PR-2026-0042."
    }

    $title = "$($Record.title)".Trim()
    if (-not $title) { return Get-ContosoProblem 'MissingTitle' "$code has no title." }

    $department = "$($Record.department)".Trim()
    if (-not $department) { return Get-ContosoProblem 'MissingDepartment' "$code has no department." }

    $budget = [decimal]::Zero
    $numberStyle = [System.Globalization.NumberStyles]::Number    # white space, sign, decimal point, thousands
    if (-not [decimal]::TryParse("$($Record.budget)", $numberStyle, $invariant, [ref] $budget) -or $budget -le 0) {
        return Get-ContosoProblem 'InvalidBudget' "$code budget '$($Record.budget)' is not a positive number."
    }

    $submitted = [datetime]::MinValue
    $dateStyle = [System.Globalization.DateTimeStyles]::None
    if (-not [datetime]::TryParseExact("$($Record.submitted)", 'yyyy-MM-dd', $invariant, $dateStyle, [ref] $submitted)) {
        return Get-ContosoProblem 'InvalidDate' "$code submitted '$($Record.submitted)' is not a yyyy-MM-dd date."
    }

    [pscustomobject]@{
        PSTypeName = 'Contoso.Request'
        Code       = $code
        Title      = $title
        Department = $department
        Budget     = $budget
        Submitted  = $submitted
        Priority   = Get-ContosoPriority -Budget $budget
    }
}
