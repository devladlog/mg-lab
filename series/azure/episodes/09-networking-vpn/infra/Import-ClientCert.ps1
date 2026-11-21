<#
.SYNOPSIS
  Imports the P2S client certificate (.pfx made by certs.sh) into the current user's personal store on Windows,
  where the Azure VPN Client and the native Windows VPN client look for it.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $PfxPath
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PfxPath)) { throw "File not found: $PfxPath" }
$password = Read-Host -Prompt 'PFX password' -AsSecureString
$cert = Import-PfxCertificate -FilePath $PfxPath -CertStoreLocation Cert:\CurrentUser\My -Password $password
[pscustomobject]@{
    Subject    = $cert.Subject
    Thumbprint = $cert.Thumbprint
    NotAfter   = $cert.NotAfter
    HasPrivateKey = $cert.HasPrivateKey
}
