#Requires -Version 7.2
<#
.SYNOPSIS
    LAB ONLY. Recreates, in the lab site, the permission drift a real site collects over a year, so the audit has
    something real to find: looser sharing settings, a person with Full Control, a list that broke inheritance for one
    person, a restricted library that copied the site's groups, a file shared on its own and an organization-wide
    edit link. Run it on the lab's Contoso Purchasing site only, never on a site people use.

    The one step it doesn't do is adding "Everyone except external users" to the Visitors group: that's done by hand
    in the browser (demo.md), the way it happens in real life.

.EXAMPLE
    ./New-PermissionDrift.ps1 -SiteUrl https://contoso.sharepoint.com/sites/Purchasing -ClientId 00000000-0000-0000-0000-000000000000 `
        -DirectUser lee.gu@contoso.com -ShareWithUser megan.bowen@contoso.com -ContractManager isaiah.langer@contoso.com -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$SiteUrl,
    [Parameter(Mandatory)][string]$ClientId,
    [Parameter(Mandatory)][string]$DirectUser,
    [Parameter(Mandatory)][string]$ShareWithUser,
    [Parameter(Mandatory)][string]$ContractManager,
    [string]$RequestsList = 'Purchase Requests',
    [string]$DocumentsList = 'Supplier Documents',
    $Connection
)

$ErrorActionPreference = 'Stop'
Import-Module PnP.PowerShell -ErrorAction Stop
$conn = if ($Connection) { $Connection } else { Connect-PnPOnline -Url $SiteUrl -ClientId $ClientId -DeviceLogin -ReturnConnection }
$c = @{}; if ($conn) { $c.Connection = $conn }

function Step([string]$What, [scriptblock]$Do) {
    if ($PSCmdlet.ShouldProcess($SiteUrl, $What)) { & $Do; Write-Host "done     $What" } else { Write-Host "what-if  $What" }
}

# 1. Site sharing settings, looser than the policy (SharePoint admin)
Step 'Sharing: existing guests, default link = people in your organization, edit' {
    Set-PnPTenantSite -Identity $SiteUrl -SharingCapability ExistingExternalUserSharingOnly -DefaultSharingLinkType Internal -DefaultLinkPermission Edit @c
}

# 2. One person with Full Control on the site, outside the owners group
Step "Full Control on the site for $DirectUser" { Set-PnPWebPermission -User $DirectUser -AddRole 'Full Control' @c }

# 3. A list that broke inheritance to give one person access
if (Get-PnPList -Identity $RequestsList @c) {
    Step "'$RequestsList': break inheritance, Contribute for $DirectUser" {
        Set-PnPList -Identity $RequestsList -BreakRoleInheritance -CopyRoleAssignments @c
        Set-PnPListPermission -Identity $RequestsList -User $DirectUser -AddRole 'Contribute' @c
    }
}
else { Write-Warning "List '$RequestsList' not found: step 3 skipped." }

# 4. The restricted library done the usual way: copy the site's groups, then add Contract Managers
Step "'$DocumentsList': Contract Managers group, break inheritance (copying the site's groups), Contribute for it" {
    if (-not (Get-PnPGroup -Identity 'Contract Managers' -ErrorAction SilentlyContinue @c)) { $null = New-PnPGroup -Title 'Contract Managers' @c }
    Add-PnPGroupMember -Group 'Contract Managers' -LoginName $ContractManager @c
    Set-PnPList -Identity $DocumentsList -BreakRoleInheritance -CopyRoleAssignments @c
    Set-PnPListPermission -Identity $DocumentsList -Group 'Contract Managers' -AddRole 'Contribute' @c
}

# 5. One contract shared with one person (the item breaks inheritance) and an organization edit link on an invoice
$items = @(Get-PnPListItem -List $DocumentsList -PageSize 500 -Fields 'FileRef', 'FileLeafRef', 'FSObjType' @c | Where-Object { "$($_['FSObjType'])" -eq '0' })
$contract = $items | Where-Object { $_['FileLeafRef'] -like 'CTR-* Fabrikam*' } | Select-Object -First 1
$invoice = $items | Where-Object { $_['FileLeafRef'] -like 'INV-* Northwind Traders*' } | Select-Object -First 1
if ($contract) {
    Step "Share '$($contract['FileLeafRef'])' with $ShareWithUser (Contribute)" {
        Set-PnPListItemPermission -List $DocumentsList -Identity $contract.Id -User $ShareWithUser -AddRole 'Contribute' @c
    }
}
else { Write-Warning 'No Fabrikam contract found (episode 4 filing): step 5a skipped.' }
if ($invoice) {
    Step "Organization edit link on '$($invoice['FileLeafRef'])'" {
        $null = Add-PnPFileOrganizationalSharingLink -FileUrl $invoice['FileRef'] -ShareType Edit @c
    }
}
else { Write-Warning 'No Northwind Traders invoice found (episode 4 filing): step 5b skipped.' }

Write-Host 'Manual step: Site permissions > Share site > add "Everyone except external users" as a Visitor (Read).' -ForegroundColor Yellow
