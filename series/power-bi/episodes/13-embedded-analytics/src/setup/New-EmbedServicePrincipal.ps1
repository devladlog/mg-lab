<#
.SYNOPSIS
  Creates what "embed for your customers" needs in the lab tenant: an Entra app + service principal with a secret,
  a security group that holds it, and the service principal as a Member of the Power BI workspace.
.DESCRIPTION
  Follows Learn "Embed Power BI content with service principal and an application secret":
  https://learn.microsoft.com/en-us/power-bi/developer/embedded/embed-service-principal
  Steps 1, 2 and 4 are done here. Step 3 (the two tenant settings, "Embed content in apps" and "Allow service principals
  to use Power BI APIs", for the security group) is done by hand in the Power BI admin portal: see demo.md.
  Needs a tenant: Microsoft.Graph (Connect-MgGraph) and MicrosoftPowerBIMgmt (Connect-PowerBIServiceAccount).
  The secret is returned as a SecureString and never written to the console or to a file.
.EXAMPLE
  $sp = ./New-EmbedServicePrincipal.ps1 -WorkspaceName 'Contoso Sales (Lab)'
  $env:PBI_TENANT_ID     = $sp.TenantId
  $env:PBI_CLIENT_ID     = $sp.ClientId
  $env:PBI_CLIENT_SECRET = ConvertFrom-SecureString -AsPlainText $sp.ClientSecret
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $AppName = 'Contoso Embed (Lab)',
    [string] $GroupName = 'Contoso Embed SPs (Lab)',
    [Parameter(Mandatory)] [string] $WorkspaceName,
    [ValidateRange(1, 24)] [int] $SecretMonths = 1
)
$ErrorActionPreference = 'Stop'

if (-not $PSCmdlet.ShouldProcess("tenant: app '$AppName', group '$GroupName', workspace '$WorkspaceName'", 'Create')) { return }

Connect-MgGraph -Scopes 'Application.ReadWrite.All', 'Group.ReadWrite.All' -NoWelcome
$tenantId = (Get-MgContext).TenantId

# Step 1: the app, its service principal and a short-lived secret. No API permissions are added on purpose
# (Learn: they are never used and can cause errors that are hard to troubleshoot).
$app = New-MgApplication -DisplayName $AppName
$sp  = New-MgServicePrincipal -AppId $app.AppId
$secret = Add-MgServicePrincipalPassword -ServicePrincipalId $sp.Id -PasswordCredential @{
    displayName = 'embed-lab'
    endDateTime = (Get-Date).AddMonths($SecretMonths)
}

# Step 2: the security group the two tenant settings will be limited to.
$group = New-MgGroup -DisplayName $GroupName -SecurityEnabled -MailEnabled:$false -MailNickName 'contosoembedsps'
New-MgGroupMember -GroupId $group.Id -DirectoryObjectId $sp.Id

# Step 4: the service principal is a Member of the workspace (Learn: Member or Admin is required).
Connect-PowerBIServiceAccount | Out-Null
$workspace = Get-PowerBIWorkspace -Filter "name eq '$WorkspaceName'"
if (-not $workspace) { throw "Workspace '$WorkspaceName' not found, or not visible to this account." }
Add-PowerBIWorkspaceUser -Id $workspace.Id -AccessRight Member -PrincipalType App -Identifier $sp.Id

[pscustomobject]@{
    TenantId           = $tenantId
    ClientId           = $app.AppId
    ServicePrincipalId = $sp.Id
    ApplicationId      = $app.Id
    GroupId            = $group.Id
    WorkspaceId        = $workspace.Id
    ClientSecret       = ConvertTo-SecureString -String $secret.SecretText -AsPlainText -Force
}
