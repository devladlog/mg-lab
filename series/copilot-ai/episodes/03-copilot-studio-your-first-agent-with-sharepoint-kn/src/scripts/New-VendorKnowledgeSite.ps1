<#
.SYNOPSIS
  Creates the SharePoint site that is the knowledge source of the Contoso Vendor Desk agent, and uploads the documents.

.DESCRIPTION
  Creates a communication site with two document libraries:
    Policies    - inherits the site permissions (owner, members and the -ReaderUpns you add to Visitors can read it)
    Restricted  - unique permissions: only -RestrictedUserUpn (and the owner) can read it
  then uploads the .docx files that `python -m kbpack build` wrote under -DocsPath\Policies and -DocsPath\Restricted.
  With -Remove it deletes the site again (tear-down).

  Needs the tenant: PnP.PowerShell 3.x and your own Entra app registration (-ClientId). PnP requires -ClientId
  for interactive sign-in since 9 September 2024; create the app once with Register-PnPEntraIDApp.
  Nothing is hard-coded: the tenant URL, the app id and the user names are parameters. Credentials are never stored.

.EXAMPLE
  ./New-VendorKnowledgeSite.ps1 -TenantUrl https://<tenant>.sharepoint.com -ClientId <app id> `
      -OwnerUpn labadmin@<tenant>.onmicrosoft.com -RestrictedUserUpn labadmin@<tenant>.onmicrosoft.com `
      -ReaderUpns sam.demo@<tenant>.onmicrosoft.com -DocsPath ./out/docs
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [Parameter(Mandatory)][ValidatePattern('^https://[a-z0-9-]+\.sharepoint\.com/?$')][string]$TenantUrl,
    [Parameter(Mandatory)][string]$ClientId,
    [Parameter(Mandatory)][string]$OwnerUpn,
    [string]$RestrictedUserUpn,
    [string[]]$ReaderUpns = @(),
    [string]$SiteAlias = 'contoso-vmo',
    [string]$SiteTitle = 'Contoso Vendor Management Office',
    [string]$DocsPath = './out/docs',
    [string]$AdminUrl,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$TenantUrl = $TenantUrl.TrimEnd('/')
$siteUrl = "$TenantUrl/sites/$SiteAlias"
# Site collections are listed in the tenant administration site: connect there to create and to delete them.
if (-not $AdminUrl) { $AdminUrl = $TenantUrl -replace '\.sharepoint\.com$', '-admin.sharepoint.com' }

Connect-PnPOnline -Url $AdminUrl -Interactive -ClientId $ClientId

if ($Remove) {
    if ($PSCmdlet.ShouldProcess($siteUrl, 'Delete the site (skip the recycle bin)')) {
        Remove-PnPTenantSite -Url $siteUrl -Force -SkipRecycleBin
        Write-Host "Removed $siteUrl"
    }
    return
}

foreach ($lib in 'Policies', 'Restricted') {
    $dir = Join-Path $DocsPath $lib
    if (-not (Test-Path -LiteralPath $dir)) { throw "Missing folder $dir. Run: python -m kbpack build --out $DocsPath" }
}

if ($PSCmdlet.ShouldProcess($siteUrl, 'Create communication site')) {
    New-PnPSite -Type CommunicationSite -Title $SiteTitle -Url $siteUrl -Owner $OwnerUpn | Out-Null
    Write-Host "Created $siteUrl"
}

Connect-PnPOnline -Url $siteUrl -Interactive -ClientId $ClientId

# People who may read the Policies library: the site's Visitors group (read-only).
foreach ($upn in $ReaderUpns) {
    if ($PSCmdlet.ShouldProcess($upn, 'Add to the site Visitors group')) {
        Add-PnPGroupMember -LoginName $upn -Group (Get-PnPGroup -AssociatedVisitorGroup)
    }
}

foreach ($lib in 'Policies', 'Restricted') {
    if ($PSCmdlet.ShouldProcess("$siteUrl/$lib", 'Create document library')) {
        New-PnPList -Title $lib -Url $lib -Template DocumentLibrary | Out-Null
    }
}

if ($RestrictedUserUpn -and $PSCmdlet.ShouldProcess("$siteUrl/Restricted", 'Break inheritance; grant read to one user')) {
    # Do not copy the inherited assignments: only the named user (and the site collection admin) can open it.
    Set-PnPList -Identity 'Restricted' -BreakRoleInheritance -CopyRoleAssignments:$false -ClearSubScopes
    # Role names are localised; these are the names on an English-language site.
    Set-PnPListPermission -Identity 'Restricted' -User $RestrictedUserUpn -AddRole 'Read'
}

$uploaded = 0
foreach ($lib in 'Policies', 'Restricted') {
    foreach ($f in Get-ChildItem -LiteralPath (Join-Path $DocsPath $lib) -Filter *.docx -File) {
        if ($PSCmdlet.ShouldProcess("$lib/$($f.Name)", 'Upload')) {
            Add-PnPFile -Path $f.FullName -Folder $lib | Out-Null
            $uploaded++
        }
    }
}
Write-Host "Uploaded $uploaded file(s)."
Write-Host "Knowledge source URL for Copilot Studio (no https://): $($siteUrl -replace '^https://','')/Policies"
