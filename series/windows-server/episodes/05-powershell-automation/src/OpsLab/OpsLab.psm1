#Requires -Version 5.1
<#
    OpsLab - least-privilege PowerShell automation for the lab.contoso.com servers (DEVLADLOG Windows Server #5).

    Part 1: a JEA endpoint from a JSON definition
        Read-OpsEndpointDefinition, Merge-OpsRoleCapability, Test-OpsEndpointDefinition, ConvertTo-OpsLintMarkdown,
        ConvertTo-OpsRoleCapabilityParams, ConvertTo-OpsSessionConfigParams, Install-OpsEndpoint
    Part 2: an unattended runbook that only talks to that endpoint
        Read-OpsJobConfig, Invoke-OpsWithRetry, Get-OpsRecentRestart, Get-OpsDecision, Write-OpsLog,
        Connect-OpsTarget, Invoke-OpsRemote, Disconnect-OpsTarget, Invoke-OpsMaintenanceRun

    Windows PowerShell 5.1 compatible on purpose (it runs on the servers and in a scheduled task);
    a Pester test parses this file and fails on PowerShell 7-only syntax.
#>
Set-StrictMode -Version 3.0

# Learn, "JEA Role Capabilities" > "Examples of potentially dangerous commands" (a starting point, not exhaustive)
$script:DangerousCommands = @(
    'Add-ADGroupMember', 'Add-LocalGroupMember', 'net.exe', 'dsadd.exe',
    'Start-Process', 'New-Service', 'Invoke-Item', 'Invoke-WmiMethod', 'Invoke-CimMethod',
    'Invoke-Expression', 'Invoke-Command', 'New-ScheduledTask', 'Register-ScheduledJob'
)
$script:StateChangingVerbs = @('Add', 'Clear', 'Disable', 'Enable', 'Install', 'Invoke', 'New', 'Remove', 'Rename',
    'Reset', 'Restart', 'Resume', 'Set', 'Start', 'Stop', 'Suspend', 'Uninstall', 'Update')
$script:ProviderRiskyCmdlets = @('Remove-Item', 'Set-Item', 'Set-Content', 'Add-Content', 'Copy-Item', 'Move-Item',
    'New-Item', 'Rename-Item', 'Clear-Content', 'Clear-Item')
$script:Severity = @{ High = 0; Medium = 1; Low = 2; Info = 3; Accepted = 4 }

function New-OpsFinding {
    param([string] $Scope, [string] $Severity, [string] $Check, [string] $Message)
    [pscustomobject]@{ Scope = $Scope; Severity = $Severity; Check = $Check; Message = $Message }
}

function Get-OpsProp {
    # StrictMode-safe property read on JSON objects and hashtables
    param($Object, [string] $Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $Default
    }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    return $Default
}

function Get-OpsPropNames {
    param($Object)
    if ($null -eq $Object) { return @() }
    if ($Object -is [System.Collections.IDictionary]) { return @($Object.Keys) }
    return @($Object.PSObject.Properties | ForEach-Object { $_.Name })
}

# ---------------------------------------------------------------------------------------------------------------
# Part 1 - the JEA endpoint
# ---------------------------------------------------------------------------------------------------------------

function Read-OpsEndpointDefinition {
    <#
    .SYNOPSIS
    Reads jea-definition.json and checks its shape (not its security; that's Test-OpsEndpointDefinition).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)

    $def = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    if ((Get-OpsProp $def 'SchemaVersion') -ne 1) { throw "Unsupported SchemaVersion in '$Path' (expected 1)." }
    foreach ($key in 'EndpointName', 'ModuleName', 'Session', 'Roles') {
        if (-not (Get-OpsProp $def $key)) { throw "'$Path' is missing '$key'." }
    }
    if (-not (Get-OpsProp $def.Session 'RoleDefinitions')) { throw "'$Path' is missing Session.RoleDefinitions." }
    if ($def.EndpointName -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') { throw "EndpointName '$($def.EndpointName)' has invalid characters." }
    if ($def.EndpointName -like 'microsoft.*') { throw "EndpointName '$($def.EndpointName)': names starting with 'microsoft' are used by Windows." }
    $def
}

function ConvertTo-OpsCommandEntry {
    <# Normalizes a VisibleCmdlets/VisibleFunctions item (string or object) to Name + Parameters ($null = unconstrained). #>
    param($Item)
    if ($Item -is [string]) { return [pscustomobject]@{ Name = $Item; Parameters = $null } }
    $params = Get-OpsProp $Item 'Parameters'
    $list = $null
    if ($null -ne $params) {
        $list = @(foreach ($p in @($params)) {
                [pscustomobject]@{
                    Name            = [string](Get-OpsProp $p 'Name')
                    ValidateSet     = @(Get-OpsProp $p 'ValidateSet' @())
                    ValidatePattern = [string](Get-OpsProp $p 'ValidatePattern' '')
                }
            })
    }
    [pscustomobject]@{ Name = [string](Get-OpsProp $Item 'Name'); Parameters = $list }
}

function Get-OpsRole {
    param($Definition, [string] $RoleName)
    $role = Get-OpsProp $Definition.Roles $RoleName
    if ($null -eq $role) { throw "Role '$RoleName' is not defined in Roles." }
    $role
}

function Merge-OpsRoleCapability {
    <#
    .SYNOPSIS
    The commands a user ends up with when several role capabilities apply, following the merge rules on Learn
    ("How role capabilities are merged"). Also lists every constraint that the merge throws away.
    .OUTPUTS
    VisibleCmdlets / VisibleFunctions (merged entries), VisibleExternalCommands, VisibleProviders, Dropped.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Definition,
        [Parameter(Mandatory)] [string[]] $RoleNames
    )

    $dropped = New-Object System.Collections.ArrayList
    $result = [ordered]@{ VisibleExternalCommands = @(); VisibleProviders = @(); Dropped = $null }

    foreach ($field in 'VisibleCmdlets', 'VisibleFunctions') {
        $byName = [ordered]@{}
        foreach ($roleName in $RoleNames) {
            $role = Get-OpsRole $Definition $roleName
            foreach ($item in @(Get-OpsProp $role $field @())) {
                $entry = ConvertTo-OpsCommandEntry $item
                $key = $entry.Name.ToLowerInvariant()
                if (-not $byName.Contains($key)) { $byName[$key] = New-Object System.Collections.ArrayList }
                [void]$byName[$key].Add([pscustomobject]@{ Role = $roleName; Entry = $entry })
            }
        }

        $merged = New-Object System.Collections.ArrayList
        foreach ($key in $byName.Keys) {
            $uses = @($byName[$key])
            $name = $uses[0].Entry.Name
            $unconstrained = @($uses | Where-Object { $null -eq $_.Entry.Parameters })
            if ($unconstrained.Count -gt 0) {
                # Rule 3: if one role doesn't constrain the parameters, all parameters are allowed
                foreach ($u in ($uses | Where-Object { $null -ne $_.Entry.Parameters })) {
                    [void]$dropped.Add([pscustomobject]@{
                            Command = $name; Parameter = '*'; Role = $u.Role; Kind = 'Merge'
                            Reason  = "role '$($unconstrained[0].Role)' allows $name with no parameter constraints, so all parameters are allowed"
                        })
                }
                [void]$merged.Add([pscustomobject]@{ Name = $name; Parameters = $null })
                continue
            }

            $paramNames = New-Object System.Collections.ArrayList
            foreach ($u in $uses) { foreach ($p in $u.Entry.Parameters) { if ($paramNames -notcontains $p.Name) { [void]$paramNames.Add($p.Name) } } }

            $mergedParams = foreach ($pn in $paramNames) {
                $defs = @(foreach ($u in $uses) {
                        foreach ($p in $u.Entry.Parameters) { if ($p.Name -eq $pn) { [pscustomobject]@{ Role = $u.Role; P = $p } } }
                    })
                $free = @($defs | Where-Object { $_.P.ValidateSet.Count -eq 0 -and -not $_.P.ValidatePattern })
                $patterns = @($defs | Where-Object { $_.P.ValidatePattern })
                $sets = @($defs | Where-Object { $_.P.ValidateSet.Count -gt 0 -and -not $_.P.ValidatePattern })
                $setAndPattern = @($defs | Where-Object { $_.P.ValidateSet.Count -gt 0 -and $_.P.ValidatePattern })
                foreach ($d in $setAndPattern) {
                    [void]$dropped.Add([pscustomobject]@{ Command = $name; Parameter = $pn; Role = $d.Role; Kind = 'SetAndPattern'
                            Reason = 'ValidateSet and ValidatePattern on the same parameter: the pattern overrides the set' })
                }

                if ($free.Count -gt 0) {
                    # Rule 4: a role allows the parameter without constraining values -> set/pattern ignored
                    foreach ($d in ($defs | Where-Object { $_.P.ValidateSet.Count -gt 0 -or $_.P.ValidatePattern })) {
                        [void]$dropped.Add([pscustomobject]@{ Command = $name; Parameter = $pn; Role = $d.Role; Kind = 'Merge'
                                Reason = "role '$($free[0].Role)' allows -$pn with any value, so this constraint is ignored" })
                    }
                    [pscustomobject]@{ Name = $pn; ValidateSet = @(); ValidatePattern = '' }
                }
                elseif ($patterns.Count -gt 0) {
                    # Rules 6 and 7: patterns are OR-ed, validate sets are ignored
                    foreach ($d in $sets) {
                        [void]$dropped.Add([pscustomobject]@{ Command = $name; Parameter = $pn; Role = $d.Role; Kind = 'Merge'
                                Reason = 'another role uses ValidatePattern on this parameter, so the ValidateSet is ignored' })
                    }
                    $joined = (@($patterns | ForEach-Object { $_.P.ValidatePattern } | Select-Object -Unique) | ForEach-Object { "(?:$_)" }) -join '|'
                    [pscustomobject]@{ Name = $pn; ValidateSet = @(); ValidatePattern = $joined }
                }
                else {
                    # Rule 5: validate sets are combined
                    $values = New-Object System.Collections.ArrayList
                    foreach ($d in $sets) { foreach ($v in $d.P.ValidateSet) { if ($values -notcontains $v) { [void]$values.Add($v) } } }
                    [pscustomobject]@{ Name = $pn; ValidateSet = @($values); ValidatePattern = '' }
                }
            }
            [void]$merged.Add([pscustomobject]@{ Name = $name; Parameters = @($mergedParams) })
        }
        $result[$field] = @($merged)
    }

    foreach ($roleName in $RoleNames) {
        $role = Get-OpsRole $Definition $roleName
        $result.VisibleExternalCommands = @($result.VisibleExternalCommands + @(Get-OpsProp $role 'VisibleExternalCommands' @()) | Select-Object -Unique)
        $result.VisibleProviders = @($result.VisibleProviders + @(Get-OpsProp $role 'VisibleProviders' @()) | Select-Object -Unique)
    }
    $result.Dropped = @($dropped)
    [pscustomobject]$result
}

function Get-OpsModuleFunction {
    <# Function names a module file defines, and the calls inside them that a JEA function must never make. #>
    param([string] $Path)
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors)
    if ($errors -and $errors.Count) { throw "Can't parse '$Path': $($errors[0].Message)" }
    $functions = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true) |
            ForEach-Object { $_.Name })
    $bad = @($ast.FindAll({
                param($n)
                ($n -is [System.Management.Automation.Language.CommandAst] -and
                @('Invoke-Expression', 'iex', 'Add-Type') -contains $n.GetCommandName()) -or
                ($n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] -and
                "$($n.Member)" -eq 'Create' -and "$($n.Expression)" -match 'scriptblock')
            }, $true) | ForEach-Object { $_.Extent.Text })
    [pscustomobject]@{ Functions = $functions; DangerousCalls = $bad }
}

function Test-OpsEndpointDefinition {
    <#
    .SYNOPSIS
    Security lint for a JEA definition: per role, per group (after merging), and for the session.
    .PARAMETER ModulePath
    The .psm1 that provides VisibleFunctions; every visible function must exist there.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Definition,
        [string] $ModulePath
    )

    $out = New-Object System.Collections.ArrayList
    $roleNames = Get-OpsPropNames $Definition.Roles
    $session = $Definition.Session
    $isDc = (Get-OpsProp $Definition 'TargetRole' 'MemberServer') -eq 'DomainController'

    # --- each role on its own
    foreach ($roleName in $roleNames) {
        $role = Get-OpsRole $Definition $roleName
        $scope = "role $roleName"
        foreach ($field in 'VisibleCmdlets', 'VisibleFunctions') {
            foreach ($item in @(Get-OpsProp $role $field @())) {
                $e = ConvertTo-OpsCommandEntry $item
                if ($e.Name -match '\*') {
                    [void]$out.Add((New-OpsFinding $scope High 'WildcardCommand' "$field '$($e.Name)' uses a wildcard: list each trusted command instead."))
                }
                if ($script:DangerousCommands -contains $e.Name) {
                    [void]$out.Add((New-OpsFinding $scope High 'DangerousCommand' "'$($e.Name)' can be used to bypass JEA (Learn's list of potentially dangerous commands)."))
                }
                $verb = ($e.Name -split '-')[0]
                if ($field -eq 'VisibleCmdlets' -and $null -eq $e.Parameters -and $script:StateChangingVerbs -contains $verb) {
                    [void]$out.Add((New-OpsFinding $scope Medium 'UnconstrainedStateChange' "'$($e.Name)' changes state and has no parameter constraints."))
                }
                foreach ($p in @($e.Parameters | Where-Object { $_ })) {
                    if ($p.ValidateSet.Count -gt 0 -and $p.ValidatePattern) {
                        [void]$out.Add((New-OpsFinding $scope Medium 'SetAndPattern' "'$($e.Name) -$($p.Name)' has ValidateSet and ValidatePattern: the pattern overrides the set."))
                    }
                    if ($p.ValidatePattern -and ($p.ValidatePattern -notmatch '^\^' -or $p.ValidatePattern -notmatch '\$$')) {
                        [void]$out.Add((New-OpsFinding $scope Low 'UnanchoredPattern' "'$($e.Name) -$($p.Name)' pattern '$($p.ValidatePattern)' isn't anchored with ^...$, so it matches anywhere in the value."))
                    }
                }
            }
        }
        foreach ($ext in @(Get-OpsProp $role 'VisibleExternalCommands' @())) {
            $leaf = Split-Path -Leaf $ext
            if ($script:DangerousCommands -contains $leaf) {
                [void]$out.Add((New-OpsFinding $scope High 'DangerousCommand' "External command '$ext' can be used to bypass JEA."))
            }
            if ($ext -notmatch '^[A-Za-z]:\\') {
                [void]$out.Add((New-OpsFinding $scope High 'ExternalCommandNotRooted' "External command '$ext' must be a full path (C:\...)."))
            }
        }
    }

    # --- the session
    $roleDefs = Get-OpsProp $session 'RoleDefinitions'
    foreach ($principal in (Get-OpsPropNames $roleDefs)) {
        if ($principal -match '^(localhost|\.)\\' -or $principal -match '\*') {
            [void]$out.Add((New-OpsFinding "group $principal" High 'BadPrincipal' "Use the computer or domain name, not localhost, '.' or wildcards."))
        }
        $assigned = @(Get-OpsProp $roleDefs $principal)
        $missing = @($assigned | Where-Object { $roleNames -notcontains $_ })
        if ($missing.Count) {
            [void]$out.Add((New-OpsFinding "group $principal" High 'UnknownRole' "Role(s) not defined: $($missing -join ', ')."))
            continue
        }

        # --- what each group really gets
        $merged = Merge-OpsRoleCapability -Definition $Definition -RoleNames $assigned
        foreach ($d in @($merged.Dropped | Where-Object { $_.Kind -eq 'Merge' })) {
            $verb = ($d.Command -split '-')[0]
            $what = "$($d.Command) -$($d.Parameter)"
            if ($d.Parameter -eq '*') { $what = $d.Command }
            $sev = 'Medium'
            if ($script:StateChangingVerbs -contains $verb) { $sev = 'High' }
            [void]$out.Add((New-OpsFinding "group $principal" $sev 'MergeWidening' "$what loses its constraint from role $($d.Role): $($d.Reason)."))
        }
        if ($merged.VisibleProviders -contains 'FileSystem') {
            $risky = @($merged.VisibleCmdlets | Where-Object { $script:ProviderRiskyCmdlets -contains $_.Name })
            if ($risky.Count) {
                [void]$out.Add((New-OpsFinding "group $principal" High 'ProviderWithFileCmdlet' "FileSystem provider plus $(($risky | ForEach-Object Name) -join ', '): arbitrary files can be changed."))
            }
        }
    }

    $runAsVa = [bool](Get-OpsProp $session 'RunAsVirtualAccount' $false)
    $vaGroups = @(Get-OpsProp $session 'RunAsVirtualAccountGroups' @())
    $gmsa = [string](Get-OpsProp $session 'GroupManagedServiceAccount' '')
    if ($runAsVa -and $vaGroups.Count -eq 0) {
        if ($isDc) {
            [void]$out.Add((New-OpsFinding 'session' High 'VirtualAccountIsAdmin' 'On a domain controller the virtual account is a member of Domain Admins.'))
        }
        else {
            [void]$out.Add((New-OpsFinding 'session' Medium 'VirtualAccountIsAdmin' 'The virtual account is a member of the local Administrators group (no RunAsVirtualAccountGroups).'))
        }
    }
    if (-not $runAsVa -and -not $gmsa) {
        [void]$out.Add((New-OpsFinding 'session' High 'NoRunAsIdentity' 'Neither RunAsVirtualAccount nor GroupManagedServiceAccount: commands run as the connecting user.'))
    }
    if ($gmsa) {
        [void]$out.Add((New-OpsFinding 'session' Low 'GmsaRunAs' 'Every user shares the gMSA identity: keep transcripts on to trace actions back to people.'))
    }
    if (-not (Get-OpsProp $session 'TranscriptDirectory')) {
        [void]$out.Add((New-OpsFinding 'session' Medium 'NoTranscript' 'No TranscriptDirectory: you lose the record of who ran what.'))
    }

    # --- the functions module
    if ($ModulePath) {
        $mod = Get-OpsModuleFunction -Path $ModulePath
        foreach ($roleName in $roleNames) {
            foreach ($item in @(Get-OpsProp (Get-OpsRole $Definition $roleName) 'VisibleFunctions' @())) {
                $fn = (ConvertTo-OpsCommandEntry $item).Name
                if ($mod.Functions -notcontains $fn) {
                    [void]$out.Add((New-OpsFinding "role $roleName" High 'FunctionNotInModule' "Visible function '$fn' isn't defined in $(Split-Path -Leaf $ModulePath)."))
                }
            }
        }
        foreach ($call in $mod.DangerousCalls) {
            [void]$out.Add((New-OpsFinding 'module' High 'DynamicCode' "The functions module runs dynamic code: '$call'. JEA functions run unconstrained."))
        }
    }

    # --- accepted risks are kept in the report, but don't count
    $accepted = @(Get-OpsProp $Definition 'AcceptedRisks' @())
    foreach ($f in $out) {
        $match = @($accepted | Where-Object { (Get-OpsProp $_ 'Check') -eq $f.Check })
        if ($match.Count -and $f.Severity -ne 'High') {
            $f.Message = "$($f.Message) Accepted: $(Get-OpsProp $match[0] 'Reason')"
            $f.Severity = 'Accepted'
        }
    }
    $out | Sort-Object { $script:Severity[$_.Severity] }, Scope, Check
}

function ConvertTo-OpsLintMarkdown {
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Definition, [object[]] $Findings = @())
    $lines = New-Object System.Collections.ArrayList
    [void]$lines.Add("# JEA lint: $($Definition.EndpointName)")
    [void]$lines.Add('')
    $count = @{}
    foreach ($s in 'High', 'Medium', 'Low', 'Info', 'Accepted') { $count[$s] = @($Findings | Where-Object Severity -eq $s).Count }
    [void]$lines.Add("High: $($count.High) | Medium: $($count.Medium) | Low: $($count.Low) | Info: $($count.Info) | Accepted: $($count.Accepted)")
    [void]$lines.Add('')
    [void]$lines.Add('## What each group gets (after merging roles)')
    [void]$lines.Add('')
    [void]$lines.Add('| Group | Roles | Commands |')
    [void]$lines.Add('|---|---|---|')
    $roleDefs = $Definition.Session.RoleDefinitions
    foreach ($principal in (Get-OpsPropNames $roleDefs)) {
        $roles = @(Get-OpsProp $roleDefs $principal)
        try { $m = Merge-OpsRoleCapability -Definition $Definition -RoleNames $roles } catch { continue }
        $cmds = foreach ($c in @($m.VisibleCmdlets) + @($m.VisibleFunctions)) {
            if ($null -eq $c.Parameters) { "$($c.Name) (any parameters)" }
            else {
                $ps = foreach ($p in $c.Parameters) {
                    if ($p.ValidateSet.Count) { "-$($p.Name) $($p.ValidateSet -join '/')" }
                    elseif ($p.ValidatePattern) { "-$($p.Name) ~$($p.ValidatePattern)" }
                    else { "-$($p.Name) (any)" }
                }
                "$($c.Name) $($ps -join ' ')"
            }
        }
        [void]$lines.Add("| $principal | $($roles -join ', ') | $(($cmds -join '<br>').Replace('|', '\|')) |")
    }
    [void]$lines.Add('')
    [void]$lines.Add('## Findings')
    [void]$lines.Add('')
    if (-not $Findings.Count) { [void]$lines.Add('None.') }
    else {
        [void]$lines.Add('| Severity | Scope | Check | Message |')
        [void]$lines.Add('|---|---|---|---|')
        foreach ($f in $Findings) { [void]$lines.Add("| $($f.Severity) | $($f.Scope) | $($f.Check) | $($f.Message.Replace('|', '\|')) |") }
    }
    ($lines -join "`n") + "`n"
}

function ConvertTo-OpsVisibleCommand {
    param($Item)
    $e = ConvertTo-OpsCommandEntry $Item
    if ($null -eq $e.Parameters) { return $e.Name }
    $params = @(foreach ($p in $e.Parameters) {
            $h = @{ Name = $p.Name }
            if ($p.ValidatePattern) { $h.ValidatePattern = $p.ValidatePattern }
            elseif ($p.ValidateSet.Count) { $h.ValidateSet = [string[]]$p.ValidateSet }
            $h
        })
    @{ Name = $e.Name; Parameters = $params }
}

function ConvertTo-OpsRoleCapabilityParams {
    <# The splat for New-PSRoleCapabilityFile for one role. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Definition, [Parameter(Mandatory)] [string] $RoleName, [Parameter(Mandatory)] [string] $Path)
    $role = Get-OpsRole $Definition $RoleName
    $p = @{
        Path            = $Path
        Description     = [string](Get-OpsProp $role 'Description' $RoleName)
        ModulesToImport = @($Definition.ModuleName)
    }
    $cmdlets = @(foreach ($i in @(Get-OpsProp $role 'VisibleCmdlets' @())) { ConvertTo-OpsVisibleCommand $i })
    $functions = @(foreach ($i in @(Get-OpsProp $role 'VisibleFunctions' @())) { ConvertTo-OpsVisibleCommand $i })
    if ($cmdlets.Count) { $p.VisibleCmdlets = $cmdlets }
    if ($functions.Count) { $p.VisibleFunctions = $functions }
    $ext = @(Get-OpsProp $role 'VisibleExternalCommands' @())
    if ($ext.Count) { $p.VisibleExternalCommands = [string[]]$ext }
    $prov = @(Get-OpsProp $role 'VisibleProviders' @())
    if ($prov.Count) { $p.VisibleProviders = [string[]]$prov }
    $p
}

function ConvertTo-OpsSessionConfigParams {
    <# The splat for New-PSSessionConfigurationFile. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] $Definition, [Parameter(Mandatory)] [string] $Path)
    $s = $Definition.Session
    $roleDefs = @{}
    foreach ($principal in (Get-OpsPropNames $s.RoleDefinitions)) {
        $roleDefs[$principal] = @{ RoleCapabilities = [string[]]@(Get-OpsProp $s.RoleDefinitions $principal) }
    }
    $p = @{
        Path            = $Path
        SessionType     = 'RestrictedRemoteServer'
        Description     = [string](Get-OpsProp $Definition 'Description' '')
        RoleDefinitions = $roleDefs
    }
    $gmsa = [string](Get-OpsProp $s 'GroupManagedServiceAccount' '')
    if ($gmsa) { $p.GroupManagedServiceAccount = $gmsa }
    elseif (Get-OpsProp $s 'RunAsVirtualAccount' $false) {
        $p.RunAsVirtualAccount = $true
        $groups = @(Get-OpsProp $s 'RunAsVirtualAccountGroups' @())
        if ($groups.Count) { $p.RunAsVirtualAccountGroups = [string[]]$groups }
    }
    $t = [string](Get-OpsProp $s 'TranscriptDirectory' '')
    if ($t) { $p.TranscriptDirectory = $t }
    $p
}

function Install-OpsEndpoint {
    <#
    .SYNOPSIS
    Builds the ContosoOps module with its RoleCapabilities, then registers the JEA endpoint. Run it ON the target, as
    an administrator, in Windows PowerShell 5.1. Registering restarts WinRM and ends every remoting session, so run
    it locally or over PowerShell Direct (Invoke-Command -VMName), not over WinRM.
    #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
    param(
        [Parameter(Mandatory)] [string] $DefinitionPath,
        [Parameter(Mandatory)] [string] $FunctionsModulePath,
        [string] $ModulesRoot = (Join-Path $env:ProgramFiles 'WindowsPowerShell\Modules'),
        [switch] $Force
    )

    $def = Read-OpsEndpointDefinition -Path $DefinitionPath
    $findings = @(Test-OpsEndpointDefinition -Definition $def -ModulePath $FunctionsModulePath)
    $high = @($findings | Where-Object Severity -eq 'High')
    if ($high.Count -and -not $Force) {
        throw "Refusing to register '$($def.EndpointName)': $($high.Count) High finding(s). First: $($high[0].Check) - $($high[0].Message)"
    }

    $moduleDir = Join-Path $ModulesRoot $def.ModuleName
    $rcDir = Join-Path $moduleDir 'RoleCapabilities'
    $steps = New-Object System.Collections.ArrayList

    if ($PSCmdlet.ShouldProcess($moduleDir, 'Create module with role capabilities')) {
        New-Item -ItemType Directory -Path $rcDir -Force | Out-Null
        $psm1 = Join-Path $moduleDir "$($def.ModuleName).psm1"
        Copy-Item -LiteralPath $FunctionsModulePath -Destination $psm1 -Force
        $functions = @(foreach ($roleName in (Get-OpsPropNames $def.Roles)) {
                foreach ($i in @(Get-OpsProp (Get-OpsRole $def $roleName) 'VisibleFunctions' @())) { (ConvertTo-OpsCommandEntry $i).Name }
            }) | Select-Object -Unique
        New-ModuleManifest -Path (Join-Path $moduleDir "$($def.ModuleName).psd1") -RootModule "$($def.ModuleName).psm1" `
            -ModuleVersion '1.0.0' -FunctionsToExport $functions -CmdletsToExport @() -VariablesToExport @() -AliasesToExport @() `
            -Description $def.Description
        $settings = Get-OpsProp $def 'Settings'
        if ($settings) {
            $settings | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $moduleDir "$($def.ModuleName).settings.json") -Encoding UTF8
        }
        foreach ($roleName in (Get-OpsPropNames $def.Roles)) {
            $params = ConvertTo-OpsRoleCapabilityParams -Definition $def -RoleName $roleName -Path (Join-Path $rcDir "$roleName.psrc")
            New-PSRoleCapabilityFile @params
        }
        [void]$steps.Add('module')
    }

    $transcripts = [string](Get-OpsProp $def.Session 'TranscriptDirectory' '')
    if ($transcripts -and $PSCmdlet.ShouldProcess($transcripts, 'Create transcript folder (SYSTEM and Administrators only)')) {
        New-Item -ItemType Directory -Path $transcripts -Force | Out-Null
        # Transcripts are written by Local System; standard users get no access. By SID, works in any language.
        & icacls.exe $transcripts /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "icacls failed on '$transcripts' (exit $LASTEXITCODE)." }
        [void]$steps.Add('transcripts')
    }

    $pssc = Join-Path ([System.IO.Path]::GetTempPath()) "$($def.EndpointName).pssc"
    $sessionParams = ConvertTo-OpsSessionConfigParams -Definition $def -Path $pssc
    if ($PSCmdlet.ShouldProcess($def.EndpointName, 'Register JEA endpoint (restarts WinRM)')) {
        New-PSSessionConfigurationFile @sessionParams
        if (-not (Test-PSSessionConfigurationFile -Path $pssc)) { throw "Test-PSSessionConfigurationFile failed for '$pssc'." }
        if (Get-PSSessionConfiguration -Name $def.EndpointName -ErrorAction SilentlyContinue) {
            Unregister-PSSessionConfiguration -Name $def.EndpointName -Force
        }
        Register-PSSessionConfiguration -Path $pssc -Name $def.EndpointName -Force | Out-Null
        Remove-Item -LiteralPath $pssc -Force -ErrorAction SilentlyContinue
        [void]$steps.Add('registered')
    }

    [pscustomobject]@{
        Endpoint = $def.EndpointName
        Module   = $moduleDir
        Steps    = @($steps)
        Findings = $findings
    }
}

# ---------------------------------------------------------------------------------------------------------------
# Part 2 - the runbook
# ---------------------------------------------------------------------------------------------------------------

function Read-OpsJobConfig {
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $Path)
    $c = Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    foreach ($key in 'EndpointName', 'Targets', 'LogDirectory', 'Retry', 'Policy') {
        if ($null -eq (Get-OpsProp $c $key)) { throw "'$Path' is missing '$key'." }
    }
    if (@($c.Targets).Count -eq 0) { throw "'$Path' has no Targets." }
    $c
}

function Get-OpsRetryDelay {
    <# Exponential backoff: base * 2^(attempt-1), capped. Attempt is 1-based (the attempt that just failed). #>
    param([int] $Attempt, [int] $BaseDelaySeconds, [int] $MaxDelaySeconds)
    $d = $BaseDelaySeconds * [math]::Pow(2, $Attempt - 1)
    [int][math]::Min($d, $MaxDelaySeconds)
}

function Invoke-OpsWithRetry {
    <#
    .SYNOPSIS
    Runs a script block, retrying with exponential backoff. Use it for reads and connections, not for changes.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [scriptblock] $ScriptBlock,
        [ValidateRange(1, 10)] [int] $MaxAttempts = 3,
        [int] $BaseDelaySeconds = 5,
        [int] $MaxDelaySeconds = 60,
        [string] $Activity = 'operation',
        [scriptblock] $Sleep = { param($Seconds) Start-Sleep -Seconds $Seconds }
    )
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            return (& $ScriptBlock)
        }
        catch {
            if ($attempt -eq $MaxAttempts) {
                throw "$Activity failed after $MaxAttempts attempt(s): $($_.Exception.Message)"
            }
            $delay = Get-OpsRetryDelay -Attempt $attempt -BaseDelaySeconds $BaseDelaySeconds -MaxDelaySeconds $MaxDelaySeconds
            Write-Verbose "$Activity attempt $attempt failed ($($_.Exception.Message)); retrying in $delay s"
            & $Sleep $delay
        }
    }
}

function Get-OpsRecentRestart {
    <#
    .SYNOPSIS
    Counts successful service restarts per computer\service in the JSON-lines logs since a point in time.
    That history is the circuit breaker: a service that keeps dying isn't restarted forever.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)] [string] $LogDirectory, [Parameter(Mandatory)] [datetime] $Since)
    $counts = @{}
    if (-not (Test-Path -LiteralPath $LogDirectory)) { return $counts }
    foreach ($file in Get-ChildItem -LiteralPath $LogDirectory -Filter 'ops-*.jsonl' -File) {
        foreach ($line in [System.IO.File]::ReadAllLines($file.FullName)) {
            if (-not $line.Trim()) { continue }
            try { $r = $line | ConvertFrom-Json } catch { continue }
            if ((Get-OpsProp $r 'Event') -ne 'Action' -or (Get-OpsProp $r 'Action') -ne 'RestartService' -or (Get-OpsProp $r 'Outcome') -ne 'Succeeded') { continue }
            # Windows PowerShell 5.1 returns the string; PowerShell 7 already converts ISO 8601 to [datetime]
            $raw = Get-OpsProp $r 'TimestampUtc'
            if ($raw -is [datetime]) {
                $ts = $raw
                if ($ts.Kind -eq [DateTimeKind]::Local) { $ts = $ts.ToUniversalTime() }
            }
            else {
                $ts = [datetime]::Parse([string]$raw, [Globalization.CultureInfo]::InvariantCulture,
                    [Globalization.DateTimeStyles]::AdjustToUniversal -bor [Globalization.DateTimeStyles]::AssumeUniversal)
            }
            if ($ts -lt $Since.ToUniversalTime()) { continue }
            $key = ('{0}\{1}' -f $r.ComputerName, $r.Target).ToUpperInvariant()
            if ($counts.ContainsKey($key)) { $counts[$key]++ } else { $counts[$key] = 1 }
        }
    }
    $counts
}

function Get-OpsDecision {
    <#
    .SYNOPSIS
    Pure decision step: health facts + policy + restart history in, actions and alerts out. Nothing is touched here.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $ComputerName,
        $Health,
        [Parameter(Mandatory)] $Policy,
        [hashtable] $RecentRestarts = @{}
    )
    $actions = New-Object System.Collections.ArrayList
    $alerts = New-Object System.Collections.ArrayList
    $alert = { param($sev, $check, $msg) [void]$alerts.Add([pscustomobject]@{ ComputerName = $ComputerName; Severity = $sev; Check = $check; Message = $msg }) }

    if ($null -eq $Health) {
        & $alert High 'Unreachable' 'No health data: endpoint unreachable or access denied.'
        return [pscustomobject]@{ ComputerName = $ComputerName; Actions = @(); Alerts = @($alerts) }
    }

    $allowed = @($Policy.RestartAllowed)
    $maxRestarts = [int](Get-OpsProp $Policy 'MaxRestartsPer24h' 3)
    foreach ($svc in @($Health.Services)) {
        switch ([string]$svc.Status) {
            'Running' { }
            'Stopped' {
                $key = ('{0}\{1}' -f $ComputerName, $svc.Name).ToUpperInvariant()
                $recent = 0
                if ($RecentRestarts.ContainsKey($key)) { $recent = $RecentRestarts[$key] }
                if ($allowed -notcontains $svc.Name) {
                    & $alert High 'ServiceStopped' "$($svc.Name) is stopped and not in RestartAllowed."
                }
                elseif ($recent -ge $maxRestarts) {
                    & $alert High 'RestartLoop' "$($svc.Name) was already restarted $recent time(s) in 24 h: not restarting again, a human needs to look."
                }
                else {
                    [void]$actions.Add([pscustomobject]@{ ComputerName = $ComputerName; Action = 'RestartService'; Target = [string]$svc.Name
                            Arguments = @{ Name = [string]$svc.Name }; Reason = "$($svc.Name) is stopped" })
                }
            }
            'Missing' { & $alert Medium 'ServiceMissing' "$($svc.Name) isn't installed on this server." }
            default { & $alert Info 'ServiceTransitional' "$($svc.Name) is $($svc.Status): left alone this run." }
        }
    }

    $retention = [int](Get-OpsProp $Policy 'LogRetentionDays' 30)
    if ([double]$Health.LogFolderMB -gt [double](Get-OpsProp $Policy 'MaxLogFolderMB' 1024)) {
        [void]$actions.Add([pscustomobject]@{ ComputerName = $ComputerName; Action = 'ClearLogs'; Target = [string]$Health.LogRoot
                Arguments = @{ OlderThanDays = $retention }
                Reason = "log folder is $($Health.LogFolderMB) MB (budget $($Policy.MaxLogFolderMB) MB)" })
    }
    if ([double]$Health.SystemFreePercent -lt [double](Get-OpsProp $Policy 'CriticalFreePercent' 10)) {
        & $alert High 'LowDisk' "System drive has $($Health.SystemFreePercent)% free."
    }
    if ($Health.RebootPending) {
        & $alert Medium 'RebootPending' 'A reboot is pending. The job never reboots: schedule it in a maintenance window.'
    }
    if ([double]$Health.UptimeDays -gt [double](Get-OpsProp $Policy 'MaxUptimeDays' 35)) {
        & $alert Low 'Uptime' "Up for $($Health.UptimeDays) days."
    }
    [pscustomobject]@{ ComputerName = $ComputerName; Actions = @($actions); Alerts = @($alerts) }
}

function Write-OpsLog {
    <# Appends one JSON object per line to ops-yyyyMMdd.jsonl (UTC day). #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $LogDirectory,
        [Parameter(Mandatory)] [hashtable] $Record,
        [Parameter(Mandatory)] [datetime] $Now
    )
    if (-not (Test-Path -LiteralPath $LogDirectory)) { New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null }
    $utc = $Now.ToUniversalTime()
    $o = [ordered]@{ TimestampUtc = $utc.ToString('yyyy-MM-ddTHH:mm:ssZ', [Globalization.CultureInfo]::InvariantCulture) }
    foreach ($k in ($Record.Keys | Sort-Object)) { $o[$k] = $Record[$k] }
    $file = Join-Path $LogDirectory ('ops-{0}.jsonl' -f $utc.ToString('yyyyMMdd', [Globalization.CultureInfo]::InvariantCulture))
    $line = ([pscustomobject]$o | ConvertTo-Json -Compress -Depth 6)
    [System.IO.File]::AppendAllText($file, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
}

function Connect-OpsTarget {
    <#
    .SYNOPSIS
    Opens a session to the JEA endpoint and imports only the commands the runbook needs, with a prefix
    (implicit remoting). JEA sessions run in NoLanguage mode, so no variables there; the proxies run locally
    in full language and send each call to the endpoint.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] [string] $ComputerName,
        [Parameter(Mandatory)] [string] $ConfigurationName,
        [pscredential] $Credential,
        [string] $Prefix = 'Jea'
    )
    $p = @{ ComputerName = $ComputerName; ConfigurationName = $ConfigurationName; ErrorAction = 'Stop' }
    if ($Credential) { $p.Credential = $Credential }
    $session = New-PSSession @p
    try {
        # Only the commands we use, by name (Learn: importing a whole JEA session can fail on the default cmdlets)
        $module = Import-PSSession -Session $session -CommandName 'Get-OpsHealth', 'Restart-Service', 'Clear-OpsLogFolder' `
            -Prefix $Prefix -AllowClobber -DisableNameChecking -ErrorAction Stop
    }
    catch {
        Remove-PSSession -Session $session
        throw
    }
    [pscustomobject]@{ ComputerName = $ComputerName; Session = $session; Module = $module; Prefix = $Prefix }
}

function Disconnect-OpsTarget {
    [CmdletBinding()]
    param($Connection)
    if ($null -eq $Connection) { return }
    if ($Connection.Module) { Remove-Module -ModuleInfo $Connection.Module -Force -ErrorAction SilentlyContinue }
    if ($Connection.Session) { Remove-PSSession -Session $Connection.Session -ErrorAction SilentlyContinue }
}

function Invoke-OpsRemote {
    <# The only three things the runbook can ask the endpoint for. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)] $Connection,
        [Parameter(Mandatory)] [ValidateSet('Health', 'RestartService', 'ClearLogs')] [string] $Operation,
        [hashtable] $Arguments = @{}
    )
    $px = $Connection.Prefix
    switch ($Operation) {
        'Health' { & "Get-${px}OpsHealth" }
        'RestartService' { & "Restart-${px}Service" -Name $Arguments.Name }
        'ClearLogs' { & "Clear-${px}OpsLogFolder" -OlderThanDays $Arguments.OlderThanDays }
    }
}

function Invoke-OpsMaintenanceRun {
    <#
    .SYNOPSIS
    One run of the runbook: for each target, read health (with retry), decide, act (no retry), log, re-check.
    .PARAMETER HealthFile
    Offline mode: decide from saved health JSON (an array), connect to nothing, change nothing.
    .OUTPUTS
    Summary with ExitCode 0 (healthy or fixed) or 1 (High alert or failed action).
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [Parameter(Mandatory)] $Config,
        [datetime] $Now = (Get-Date),
        [string] $HealthFile,
        [pscredential] $Credential,
        [string] $RunId = ([guid]::NewGuid().ToString())
    )

    $logDir = [string]$Config.LogDirectory
    $offline = [bool]$HealthFile
    $saved = @{}
    if ($offline) {
        foreach ($h in @(Get-Content -Raw -LiteralPath $HealthFile | ConvertFrom-Json)) { $saved[([string]$h.ComputerName).ToUpperInvariant()] = $h }
    }
    $runAs = '{0}\{1}' -f [Environment]::UserDomainName, [Environment]::UserName
    $log = { param([hashtable] $r) $r.RunId = $RunId; $r.RunAs = $runAs; Write-OpsLog -LogDirectory $logDir -Record $r -Now $Now }
    & $log @{ Event = 'RunStart'; Targets = @($Config.Targets); Mode = $(if ($offline) { 'Offline' } else { 'Live' }) }

    $recent = Get-OpsRecentRestart -LogDirectory $logDir -Since $Now.AddHours(-24)
    $results = New-Object System.Collections.ArrayList
    $failed = 0

    foreach ($target in @($Config.Targets)) {
        $conn = $null
        $health = $null
        try {
            if ($offline) {
                $health = $saved[([string]$target).ToUpperInvariant()]
            }
            else {
                $r = $Config.Retry
                $conn = Invoke-OpsWithRetry -Activity "connect to $target" -MaxAttempts $r.MaxAttempts -BaseDelaySeconds $r.BaseDelaySeconds -MaxDelaySeconds $r.MaxDelaySeconds -ScriptBlock {
                    Connect-OpsTarget -ComputerName $target -ConfigurationName $Config.EndpointName -Credential $Credential
                }
                $health = Invoke-OpsWithRetry -Activity "health of $target" -MaxAttempts $r.MaxAttempts -BaseDelaySeconds $r.BaseDelaySeconds -MaxDelaySeconds $r.MaxDelaySeconds -ScriptBlock {
                    Invoke-OpsRemote -Connection $conn -Operation Health
                }
            }
        }
        catch {
            & $log @{ Event = 'Error'; ComputerName = $target; Message = $_.Exception.Message }
        }

        $decision = Get-OpsDecision -ComputerName $target -Health $health -Policy $Config.Policy -RecentRestarts $recent
        if ($health) {
            & $log @{ Event = 'Health'; ComputerName = $target; Services = @($health.Services | ForEach-Object { "$($_.Name)=$($_.Status)" })
                SystemFreePercent = $health.SystemFreePercent; LogFolderMB = $health.LogFolderMB; RebootPending = [bool]$health.RebootPending }
        }
        foreach ($a in $decision.Alerts) { & $log @{ Event = 'Alert'; ComputerName = $target; Severity = $a.Severity; Check = $a.Check; Message = $a.Message } }

        $actionResults = New-Object System.Collections.ArrayList
        foreach ($action in $decision.Actions) {
            $outcome = 'Planned'
            $detail = $action.Reason
            if (-not $offline -and $PSCmdlet.ShouldProcess("$target $($action.Target)", $action.Action)) {
                try {
                    # No retry here: a change that half-happened is not retried blindly
                    $res = Invoke-OpsRemote -Connection $conn -Operation $action.Action -Arguments $action.Arguments
                    $outcome = 'Succeeded'
                    if ($action.Action -eq 'ClearLogs' -and $res) { $detail = "$($res.FilesRemoved) file(s), $($res.MBFreed) MB freed" }
                }
                catch {
                    $outcome = 'Failed'
                    $detail = $_.Exception.Message
                    $failed++
                }
            }
            & $log @{ Event = 'Action'; ComputerName = $target; Action = $action.Action; Target = $action.Target; Outcome = $outcome; Detail = $detail }
            [void]$actionResults.Add([pscustomobject]@{ Action = $action.Action; Target = $action.Target; Outcome = $outcome; Detail = $detail })
        }

        # Re-check after a restart: the job reports what it sees, not what it hoped for
        if (-not $offline -and @($actionResults | Where-Object { $_.Action -eq 'RestartService' -and $_.Outcome -eq 'Succeeded' }).Count) {
            try {
                $after = Invoke-OpsRemote -Connection $conn -Operation Health
                foreach ($svc in @($after.Services)) {
                    if (@($actionResults | Where-Object { $_.Target -eq $svc.Name }).Count -and [string]$svc.Status -ne 'Running') {
                        & $log @{ Event = 'Alert'; ComputerName = $target; Severity = 'High'; Check = 'RestartDidNotHold'; Message = "$($svc.Name) is $($svc.Status) after restart." }
                        $decision.Alerts += [pscustomobject]@{ ComputerName = $target; Severity = 'High'; Check = 'RestartDidNotHold'; Message = "$($svc.Name) is $($svc.Status) after restart." }
                    }
                }
            }
            catch { & $log @{ Event = 'Error'; ComputerName = $target; Message = "Re-check failed: $($_.Exception.Message)" } }
        }
        Disconnect-OpsTarget -Connection $conn

        [void]$results.Add([pscustomobject]@{
                ComputerName = $target
                Reachable    = [bool]$health
                Actions      = @($actionResults)
                Alerts       = @($decision.Alerts)
            })
    }

    $highAlerts = @($results | ForEach-Object { $_.Alerts } | Where-Object { $_.Severity -eq 'High' })
    $exit = 0
    if ($failed -gt 0 -or $highAlerts.Count -gt 0) { $exit = 1 }
    & $log @{ Event = 'RunEnd'; ExitCode = $exit; Failed = $failed; HighAlerts = $highAlerts.Count }
    [pscustomobject]@{ RunId = $RunId; Results = @($results); ExitCode = $exit }
}

Export-ModuleMember -Function Read-OpsEndpointDefinition, Merge-OpsRoleCapability, Test-OpsEndpointDefinition,
ConvertTo-OpsLintMarkdown, ConvertTo-OpsRoleCapabilityParams, ConvertTo-OpsSessionConfigParams, Install-OpsEndpoint,
Get-OpsModuleFunction, Read-OpsJobConfig, Get-OpsRetryDelay, Invoke-OpsWithRetry, Get-OpsRecentRestart, Get-OpsDecision,
Write-OpsLog, Connect-OpsTarget, Disconnect-OpsTarget, Invoke-OpsRemote, Invoke-OpsMaintenanceRun
