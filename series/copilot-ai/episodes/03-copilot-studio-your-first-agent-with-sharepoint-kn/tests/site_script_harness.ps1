# Test harness only: defines stand-ins for the PnP.PowerShell cmdlets, runs src/scripts/New-VendorKnowledgeSite.ps1
# and writes every call to a JSON file. Nothing here talks to SharePoint.
param([string]$Script, [string]$CallLog, [string]$ArgsJson)

$global:Calls = [System.Collections.Generic.List[object]]::new()
function global:Rec([string]$name, $bound) {
    $h = [ordered]@{ cmd = $name }
    foreach ($k in $bound.Keys) { $h[$k] = "$($bound[$k])" }
    $global:Calls.Add($h)
}
function global:Connect-PnPOnline { [CmdletBinding()] param($Url, [switch]$Interactive, $ClientId) Rec 'Connect-PnPOnline' $PSBoundParameters }
function global:New-PnPSite { [CmdletBinding()] param($Type, $Title, $Url, $Owner) Rec 'New-PnPSite' $PSBoundParameters }
function global:New-PnPList { [CmdletBinding()] param($Title, $Url, $Template) Rec 'New-PnPList' $PSBoundParameters }
function global:Set-PnPList { [CmdletBinding()] param($Identity, [switch]$BreakRoleInheritance, [switch]$CopyRoleAssignments, [switch]$ClearSubScopes) Rec 'Set-PnPList' $PSBoundParameters }
function global:Set-PnPListPermission { [CmdletBinding()] param($Identity, $User, $AddRole) Rec 'Set-PnPListPermission' $PSBoundParameters }
function global:Get-PnPGroup { [CmdletBinding()] param([switch]$AssociatedVisitorGroup) Rec 'Get-PnPGroup' $PSBoundParameters; 'Visitors-stand-in' }
function global:Add-PnPGroupMember { [CmdletBinding()] param($LoginName, $Group) Rec 'Add-PnPGroupMember' $PSBoundParameters }
function global:Add-PnPFile { [CmdletBinding()] param($Path, $Folder) $b = @{ File = (Split-Path $Path -Leaf); Folder = $Folder }; Rec 'Add-PnPFile' $b }
function global:Remove-PnPTenantSite { [CmdletBinding()] param($Url, [switch]$Force, [switch]$SkipRecycleBin) Rec 'Remove-PnPTenantSite' $PSBoundParameters }

$splat = @{}
(Get-Content -Raw $ArgsJson | ConvertFrom-Json).PSObject.Properties | ForEach-Object {
    $splat[$_.Name] = if ($_.Value -is [bool] -and $_.Value) { [switch]::Present } else { $_.Value }
}
$err = $null
try { & $Script @splat | Out-Null } catch { $err = $_.Exception.Message }
@{ calls = $global:Calls; error = $err } | ConvertTo-Json -Depth 5 | Set-Content -Path $CallLog
