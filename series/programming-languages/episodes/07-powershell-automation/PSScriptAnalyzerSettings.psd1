@{
    # The gate: anything at Warning or Error fails ./build.ps1
    Severity     = @('Error', 'Warning')
    ExcludeRules = @()
}
