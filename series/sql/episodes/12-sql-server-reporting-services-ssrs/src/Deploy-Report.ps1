<#
.SYNOPSIS
  Publishes SalesByProduct.rdl to a native-mode report server with the ReportService2010 SOAP endpoint.
.DESCRIPTION
  Creates the folder /MGLab, the shared data source /MGLab/ContosoBikesRpt (stored credentials of the SQL login rs_reader)
  and the report /MGLab/SalesByProduct, then points the report at the shared data source.
  Needs a report server (needs tenant: not run in the build sandbox). Windows PowerShell 5.1 (New-WebServiceProxy
  is not in PowerShell 7). The password comes from the environment variable RS_READER_PASSWORD, never from a file.
.EXAMPLE
  $env:RS_READER_PASSWORD = Read-Host 'rs_reader password'
  .\Deploy-Report.ps1 -ReportServer http://CON-SRV02/ReportServer -SqlServer CON-SQL01
#>
[CmdletBinding()]
param(
    [string]$ReportServer = 'http://CON-SRV02/ReportServer',
    [string]$SqlServer    = 'CON-SQL01',
    [string]$RdlPath      = (Join-Path $PSScriptRoot 'report\SalesByProduct.rdl'),
    [string]$Folder       = 'MGLab',
    [switch]$Remove
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Connect-ReportService([string]$ReportServer) {
    $url = $ReportServer.TrimEnd('/') + '/ReportService2010.asmx?wsdl'
    New-WebServiceProxy -Uri $url -UseDefaultCredential -Namespace RS2010
}

function Set-RsFolder($Proxy, [string]$Name) {
    try { $null = $Proxy.CreateFolder($Name, '/', $null) }
    catch [System.Web.Services.Protocols.SoapException] {
        if ($_.Exception.Detail.InnerText -notmatch 'rsItemAlreadyExists') { throw }
    }
}

function Set-RsDataSource($Proxy, [string]$Parent, [string]$Name, [string]$SqlServer, [string]$Password) {
    $def = New-Object RS2010.DataSourceDefinition
    $def.Extension           = 'SQL'
    $def.ConnectString       = "Data Source=$SqlServer;Initial Catalog=ContosoBikesRpt;Encrypt=True;TrustServerCertificate=True"
    $def.CredentialRetrieval = [RS2010.CredentialRetrievalEnum]::Store
    $def.UserName            = 'rs_reader'
    $def.Password            = $Password
    $def.WindowsCredentials  = $false
    $def.Enabled             = $true
    $def.EnabledSpecified    = $true
    $null = $Proxy.CreateDataSource($Name, $Parent, $true, $def, $null)
}

function Publish-RsReport($Proxy, [string]$Parent, [string]$RdlPath, [string]$DataSourcePath) {
    $name  = [IO.Path]::GetFileNameWithoutExtension($RdlPath)
    $bytes = [IO.File]::ReadAllBytes($RdlPath)
    $warnings = $null
    $null = $Proxy.CreateCatalogItem('Report', $name, $Parent, $true, $bytes, $null, [ref]$warnings)
    foreach ($w in $warnings) { Write-Warning $w.Message }
    $ref = New-Object RS2010.DataSourceReference
    $ref.Reference = $DataSourcePath
    $ds = New-Object RS2010.DataSource
    $ds.Name = 'ContosoBikesRpt'
    $ds.Item = $ref
    $Proxy.SetItemDataSources("$Parent/$name", @($ds))
}

if ($MyInvocation.InvocationName -ne '.') {
    $proxy = Connect-ReportService $ReportServer
    if ($Remove) {
        $proxy.DeleteItem("/$Folder")
        Write-Host "Removed /$Folder"
        return
    }
    if (-not $env:RS_READER_PASSWORD) { throw 'Set RS_READER_PASSWORD (the password of the SQL login rs_reader).' }
    Set-RsFolder $proxy $Folder
    Set-RsDataSource $proxy "/$Folder" 'ContosoBikesRpt' $SqlServer $env:RS_READER_PASSWORD
    Publish-RsReport $proxy "/$Folder" $RdlPath "/$Folder/ContosoBikesRpt"
    Write-Host "Published: $($ReportServer.Replace('/ReportServer','/Reports'))/report/$Folder/SalesByProduct"
}
