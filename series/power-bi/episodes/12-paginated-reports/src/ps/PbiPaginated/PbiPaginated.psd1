@{
    RootModule        = 'PbiPaginated.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-00000000c012'
    Author            = 'Momento Galatico'
    Description       = 'Paginated reports (.rdl) through the Power BI REST API: import, export, wait, download.'
    PowerShellVersion = '7.2'
    FunctionsToExport = @('New-PbiMultipartFile', 'Import-PbiRdl', 'Wait-PbiImport', 'New-PbiExportRequest', 'Start-PbiExport', 'Wait-PbiExport', 'Save-PbiExport', 'Export-PbiPaginatedReport')
}
