Set-StrictMode -Version Latest

# AdminGate: a review gate for PowerShell that an AI assistant (or a colleague) wrote.
# It parses the script with the PowerShell parser and walks the syntax tree. It never runs the script.
# It is a second pair of eyes, not a security boundary: Azure RBAC, JEA and your own permissions are.

$script:AliasMap = @{
    'iex' = 'Invoke-Expression'; 'rm' = 'Remove-Item'; 'ri' = 'Remove-Item'; 'del' = 'Remove-Item'
    'erase' = 'Remove-Item'; 'rd' = 'Remove-Item'; 'rmdir' = 'Remove-Item'; 'ni' = 'New-Item'
    'mv' = 'Move-Item'; 'move' = 'Move-Item'; 'mi' = 'Move-Item'; 'cp' = 'Copy-Item'; 'copy' = 'Copy-Item'
    'cpi' = 'Copy-Item'; 'sc' = 'Set-Content'; 'ac' = 'Add-Content'; 'kill' = 'Stop-Process'
    'spps' = 'Stop-Process'; 'saps' = 'Start-Process'; 'start' = 'Start-Process'; 'sasv' = 'Start-Service'
    'spsv' = 'Stop-Service'; 'rv' = 'Remove-Variable'; 'sv' = 'Set-Variable'; 'set' = 'Set-Variable'
    'si' = 'Set-Item'; 'rni' = 'Rename-Item'; 'ren' = 'Rename-Item'; 'clc' = 'Clear-Content'
}

$script:ChangeVerbs = @(
    'Set', 'New', 'Remove', 'Add', 'Clear', 'Disable', 'Enable', 'Install', 'Uninstall', 'Restart', 'Stop',
    'Start', 'Update', 'Move', 'Rename', 'Copy', 'Format', 'Initialize', 'Grant', 'Revoke', 'Block', 'Unblock',
    'Reset', 'Resize', 'Repair', 'Register', 'Unregister', 'Suspend', 'Resume', 'Mount', 'Dismount', 'Publish',
    'Out'
)

# Commands whose verb looks like a change but only touch the current session or console.
$script:NotAChange = @(
    'New-Object', 'New-Guid', 'New-TimeSpan', 'New-Variable', 'New-Alias', 'New-PSSession', 'New-PSDrive',
    'New-CimSession', 'New-CimSessionOption', 'New-PSSessionOption', 'New-ScriptFileInfo',
    'Set-StrictMode', 'Set-Location', 'Set-Variable', 'Set-Alias', 'Set-PSDebug', 'Set-PSReadLineOption',
    'Remove-Variable', 'Remove-Module', 'Remove-PSSession', 'Remove-CimSession', 'Remove-PSDrive',
    'Remove-Alias', 'Start-Sleep', 'Start-Transcript', 'Stop-Transcript', 'Clear-Host', 'Clear-Variable',
    'Add-Type', 'Add-Member', 'Out-Null', 'Out-String', 'Out-Host', 'Out-Default', 'Out-GridView',
    'Update-TypeData', 'Update-FormatData', 'Register-ArgumentCompleter', 'Register-ObjectEvent', 'Unregister-Event'
)

$script:DestructiveByName = @(
    'Format-Volume', 'Clear-Disk', 'Initialize-Disk', 'Remove-Partition', 'Remove-VM', 'Remove-VHD',
    'Stop-Computer', 'Uninstall-ADDSDomainController', 'Remove-ADObject', 'Remove-ADUser',
    'Remove-ADComputer', 'Remove-ADGroup', 'Remove-ADOrganizationalUnit', 'Remove-StoragePool',
    'Remove-VirtualDisk', 'Reset-PhysicalDisk'
)

$script:FanOutSources = @(
    'Get-ADComputer', 'Get-ADUser', 'Get-ADGroup', 'Get-ADGroupMember', 'Get-Content', 'Import-Csv',
    'Get-VM', 'Get-Service', 'Get-Process', 'Get-ChildItem', 'Get-NetFirewallRule', 'Get-ScheduledTask',
    'Get-LocalUser'
)

$script:CommonParameters = @(
    'Verbose', 'Debug', 'ErrorAction', 'WarningAction', 'InformationAction', 'ErrorVariable', 'WarningVariable',
    'InformationVariable', 'OutVariable', 'OutBuffer', 'PipelineVariable', 'ProgressAction'
)

function Resolve-CanonicalName {
    param([string] $Name)
    if ($script:AliasMap.ContainsKey($Name.ToLowerInvariant())) { return $script:AliasMap[$Name.ToLowerInvariant()] }
    return $Name
}

function Test-IsChangeCommand {
    param([string] $Name)
    $canonical = Resolve-CanonicalName $Name
    foreach ($n in $script:NotAChange) { if ($n -ieq $canonical) { return $false } }
    if ($canonical -match '^(?<verb>[A-Za-z]+)-') {
        foreach ($v in $script:ChangeVerbs) { if ($v -ieq $Matches['verb']) { return $true } }
    }
    return $false
}

function Get-WhatIfState {
    # Returns 'Literal' for -WhatIf / -WhatIf:$true, 'Propagated' for -WhatIf:$var, 'Off' for -WhatIf:$false, 'None'.
    param($CommandAst)
    foreach ($el in $CommandAst.CommandElements) {
        if ($el -is [System.Management.Automation.Language.CommandParameterAst] -and
            $el.ParameterName.Length -ge 3 -and 'WhatIf'.StartsWith($el.ParameterName, [System.StringComparison]::OrdinalIgnoreCase)) {
            if ($null -eq $el.Argument) { return 'Literal' }
            $text = $el.Argument.Extent.Text
            if ($text -ieq '$true') { return 'Literal' }
            if ($text -ieq '$false') { return 'Off' }
            return 'Propagated'
        }
    }
    return 'None'
}

function Get-NamedParameter {
    param($CommandAst, [string[]] $Names)
    foreach ($el in $CommandAst.CommandElements) {
        if ($el -is [System.Management.Automation.Language.CommandParameterAst]) {
            foreach ($n in $Names) {
                if ($el.ParameterName -ieq $n) { return $el }
            }
        }
    }
    return $null
}

function Test-ScopeSupportsShouldProcess {
    param($Ast)
    $node = $Ast.Parent
    while ($null -ne $node) {
        $paramBlock = $null
        if ($node -is [System.Management.Automation.Language.FunctionDefinitionAst]) { $paramBlock = $node.Body.ParamBlock }
        elseif ($node -is [System.Management.Automation.Language.ScriptBlockAst] -and $null -eq $node.Parent) { $paramBlock = $node.ParamBlock }
        if ($null -ne $paramBlock) {
            foreach ($attr in $paramBlock.Attributes) {
                if ($attr.TypeName.Name -ieq 'CmdletBinding') {
                    foreach ($na in $attr.NamedArguments) {
                        if ($na.ArgumentName -ieq 'SupportsShouldProcess') {
                            if ($na.ExpressionOmitted) { return $true }
                            return ($na.Argument.Extent.Text -ine '$false')
                        }
                    }
                }
            }
        }
        $node = $node.Parent
    }
    return $false
}

function Get-StringValue {
    param($Ast)
    if ($Ast -is [System.Management.Automation.Language.StringConstantExpressionAst]) { return $Ast.Value }
    return $null
}

function Test-DangerousRemoveTarget {
    param($CommandAst)
    $recurse = Get-NamedParameter $CommandAst @('Recurse')
    if ($null -eq $recurse) { return $false }
    foreach ($el in $CommandAst.CommandElements | Select-Object -Skip 1) {
        $v = Get-StringValue $el
        if ($null -ne $v -and $v -match '^(?:[A-Za-z]:\\?\*?|/\*?|\\\*?|[A-Za-z]:\\(?:Windows|Users|Program Files)\\?\*?)$') { return $true }
    }
    return $false
}

function Test-AdminScript {
    <#
    .SYNOPSIS
    Reviews a PowerShell script without running it.
    .PARAMETER Mode
    ReadOnly: any state-changing command is a BLOCK unless it carries a literal -WhatIf. Change: changes are allowed but reviewed.
    .PARAMETER CommandResolver
    Script block that takes a command name and returns an object with a Parameters dictionary, or $null. Default: Get-Command.
    .PARAMETER SkipResolution
    Do not check that commands and parameters exist (use on a machine that lacks the modules, such as a build agent).
    #>
    [CmdletBinding(DefaultParameterSetName = 'Text')]
    param(
        [Parameter(Mandatory, ParameterSetName = 'Text', ValueFromPipeline)] [string] $ScriptText,
        [Parameter(Mandatory, ParameterSetName = 'Path')] [string] $Path,
        [ValidateSet('ReadOnly', 'Change')] [string] $Mode = 'ReadOnly',
        [scriptblock] $CommandResolver = { param($Name) Get-Command -Name $Name -ErrorAction SilentlyContinue | Select-Object -First 1 },
        [switch] $SkipResolution
    )
    process {
        if ($PSCmdlet.ParameterSetName -eq 'Path') { $ScriptText = Get-Content -LiteralPath $Path -Raw }
        $tokens = $null; $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseInput($ScriptText, [ref] $tokens, [ref] $errors)
        $findings = [System.Collections.Generic.List[object]]::new()
        $add = {
            param($Rule, $Severity, $Line, $Message)
            $findings.Add([pscustomobject]@{ Rule = $Rule; Severity = $Severity; Line = $Line; Message = $Message })
        }

        foreach ($e in $errors) {
            & $add 'AG-X001' 'Block' $e.Extent.StartLineNumber ("Does not parse: " + $e.Message)
        }

        $definedFunctions = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true) | ForEach-Object { $_.Name })
        $commands = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] }, $true))

        foreach ($cmd in $commands) {
            $name = $cmd.GetCommandName()
            if ([string]::IsNullOrEmpty($name)) { continue }
            $canonical = Resolve-CanonicalName $name
            $line = $cmd.Extent.StartLineNumber
            $isChange = Test-IsChangeCommand $name
            $whatIf = Get-WhatIfState $cmd

            # AG-D001 dangerous execution patterns
            if ($canonical -ieq 'Invoke-Expression') {
                & $add 'AG-D001' 'Block' $line 'Invoke-Expression runs text as code; write the command out instead'
            }
            if ($canonical -match '^(?:powershell|pwsh)(?:\.exe)?$') {
                foreach ($el in $cmd.CommandElements) {
                    if ($el -is [System.Management.Automation.Language.CommandParameterAst] -and
                        $el.ParameterName -match '^(?:e|ec|en|enc|enco|encod|encode|encoded|encodedc|encodedco|encodedcom|encodedcomm|encodedcomma|encodedcomman|encodedcommand)$') {
                        & $add 'AG-D001' 'Block' $line 'Encoded command hides what will run'
                    }
                }
            }
            if ($canonical -ieq 'Set-ExecutionPolicy') {
                $text = $cmd.Extent.Text
                if ($text -match '(?i)\b(?:Bypass|Unrestricted)\b') {
                    & $add 'AG-D001' 'Block' $line 'Set-ExecutionPolicy Bypass or Unrestricted switches script checks off'
                }
            }

            # AG-D002 destructive commands
            $destructive = $false
            foreach ($d in $script:DestructiveByName) { if ($d -ieq $canonical) { $destructive = $true } }
            if ($canonical -ieq 'Remove-Item' -and (Test-DangerousRemoveTarget $cmd)) { $destructive = $true }
            if ($canonical -ieq 'Set-NetFirewallProfile' -and $cmd.Extent.Text -match '(?i)-Enabled\s+(?:False|0|\$false)') { $destructive = $true }
            if ($canonical -ieq 'Set-MpPreference' -and $cmd.Extent.Text -match '(?i)-Disable\w+\s+(?:\$true|1|True)') { $destructive = $true }
            if ($destructive -and $whatIf -ne 'Literal') {
                & $add 'AG-D002' 'Block' $line "$canonical can destroy data or switch protection off; only with a literal -WhatIf"
            }

            if ($isChange) {
                # AG-M001 read-only mode
                if ($Mode -eq 'ReadOnly' -and $whatIf -ne 'Literal') {
                    & $add 'AG-M001' 'Block' $line "$canonical changes state, but the mode is ReadOnly"
                }
                # AG-C001 no SupportsShouldProcess
                if ($whatIf -eq 'None' -and -not (Test-ScopeSupportsShouldProcess $cmd)) {
                    & $add 'AG-C001' 'Warn' $line "$canonical changes state and the enclosing script or function has no SupportsShouldProcess, so -WhatIf cannot protect it"
                }
                # AG-C002 -Confirm:$false / -Force
                $confirm = Get-NamedParameter $cmd @('Confirm')
                if ($null -ne $confirm -and $null -ne $confirm.Argument -and $confirm.Argument.Extent.Text -ieq '$false') {
                    & $add 'AG-C002' 'Warn' $line "$canonical -Confirm:`$false removes the last prompt"
                }
                if ($null -ne (Get-NamedParameter $cmd @('Force'))) {
                    & $add 'AG-C002' 'Warn' $line "$canonical -Force overrides safety checks"
                }
            }

            # AG-S001 plaintext secrets in commands
            if ($canonical -ieq 'ConvertTo-SecureString' -and $null -ne (Get-NamedParameter $cmd @('AsPlainText'))) {
                & $add 'AG-S001' 'Block' $line 'ConvertTo-SecureString -AsPlainText puts a secret in the script'
            }
            $elements = @($cmd.CommandElements)
            for ($i = 0; $i -lt $elements.Count; $i++) {
                $el = $elements[$i]
                if ($el -is [System.Management.Automation.Language.CommandParameterAst] -and $el.ParameterName -match '(?i)^(?:password|secret|token|apikey)$') {
                    $value = $el.Argument
                    if ($null -eq $value -and $i + 1 -lt $elements.Count -and $elements[$i + 1] -isnot [System.Management.Automation.Language.CommandParameterAst]) { $value = $elements[$i + 1] }
                    $lit = if ($null -ne $value) { Get-StringValue $value } else { $null }
                    if ($null -ne $lit) { & $add 'AG-S001' 'Block' $line "A literal value is passed to -$($el.ParameterName)" }
                }
            }

            # AG-H001 / AG-H002 hallucination checks
            if (-not $SkipResolution -and $definedFunctions -notcontains $name) {
                $info = & $CommandResolver $name
                if ($null -eq $info) {
                    & $add 'AG-H001' 'Warn' $line "Command '$name' was not found on this machine: typo, invented cmdlet, or module not installed"
                }
                elseif ($info.PSObject.Properties.Name -contains 'Parameters' -and $null -ne $info.Parameters -and $info.Parameters.Count -gt 0) {
                    $known = @($info.Parameters.Keys)
                    $aliases = @($info.Parameters.Values | ForEach-Object { if ($_.PSObject.Properties.Name -contains 'Aliases') { $_.Aliases } })
                    $all = @($known) + @($aliases) + $script:CommonParameters
                    foreach ($el in $cmd.CommandElements) {
                        if ($el -isnot [System.Management.Automation.Language.CommandParameterAst]) { continue }
                        $p = $el.ParameterName
                        $hit = $all | Where-Object { $_ -ieq $p -or $_.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase) }
                        if (-not $hit) {
                            & $add 'AG-H002' 'Block' $line "Command '$name' has no parameter -$p"
                        }
                    }
                }
            }
        }

        # AG-R001 fan-out: a collection pipes into a change
        $pipelines = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.PipelineAst] }, $true))
        foreach ($pl in $pipelines) {
            if ($pl.PipelineElements.Count -lt 2) { continue }
            $first = $pl.PipelineElements[0]
            if ($first -isnot [System.Management.Automation.Language.CommandAst]) { continue }
            $firstName = Resolve-CanonicalName ([string] $first.GetCommandName())
            $isSource = $false
            foreach ($s in $script:FanOutSources) { if ($s -ieq $firstName) { $isSource = $true } }
            if (-not $isSource) { continue }
            foreach ($el in ($pl.PipelineElements | Select-Object -Skip 1)) {
                if ($el -is [System.Management.Automation.Language.CommandAst] -and (Test-IsChangeCommand ([string] $el.GetCommandName()))) {
                    & $add 'AG-R001' 'Warn' $el.Extent.StartLineNumber "$firstName fans out to $(Resolve-CanonicalName $el.GetCommandName()): try one item with -WhatIf first"
                }
            }
        }

        # AG-S001 plaintext secrets in assignments
        $assignments = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] }, $true))
        foreach ($as in $assignments) {
            if ($as.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
                $as.Left.VariablePath.UserPath -match '(?i)(?:password|passwd|secret|token|apikey)') {
                $right = $as.Right
                if ($right -is [System.Management.Automation.Language.CommandExpressionAst]) {
                    $lit = Get-StringValue $right.Expression
                    if ($null -ne $lit -and $lit.Length -gt 0) {
                        & $add 'AG-S001' 'Block' $as.Extent.StartLineNumber "Variable `$$($as.Left.VariablePath.UserPath) is assigned a literal secret"
                    }
                }
            }
        }

        # AG-T001 empty catch
        $catches = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CatchClauseAst] }, $true))
        foreach ($c in $catches) {
            if ($c.Body.Statements.Count -eq 0) {
                & $add 'AG-T001' 'Warn' $c.Extent.StartLineNumber 'Empty catch block hides failures'
            }
        }

        $sorted = @($findings | Sort-Object Line, Rule)
        $blocks = @($sorted | Where-Object Severity -eq 'Block').Count
        $warns = @($sorted | Where-Object Severity -eq 'Warn').Count
        $exit = if ($blocks -gt 0) { 2 } elseif ($warns -gt 0) { 1 } else { 0 }
        $verdict = switch ($exit) { 2 { 'Blocked' } 1 { 'Warnings' } default { 'Clean' } }
        [pscustomobject]@{
            Mode = $Mode; Verdict = $verdict; ExitCode = $exit; Blocks = $blocks; Warnings = $warns; Findings = $sorted
        }
    }
}

Export-ModuleMember -Function Test-AdminScript
