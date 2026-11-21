# Writes verify-results\toolchain.txt: which tools the Windows recording laptop has (read-only).
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$out = Join-Path $Root 'verify-results'; New-Item -ItemType Directory -Force -Path $out | Out-Null
$lines = @("Run: $(Get-Date -Format s)", "OS: $([Environment]::OSVersion.VersionString)", "Windows PowerShell: $($PSVersionTable.PSVersion)")
function T($label, [scriptblock]$sb) { try { $v = (& $sb 2>&1 | Out-String).Trim() } catch { $v = "missing ($($_.Exception.Message))" }; $script:lines += "== $label ==", $v }
T 'dotnet --info (SDKs)' { dotnet --list-sdks }
T 'dotnet workloads' { dotnet workload list }
T 'pwsh' { pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString(); (Get-Module -ListAvailable Pester | Sort-Object Version -Descending | Select-Object -First 3 | ForEach-Object { "Pester " + $_.Version }) -join "; "' }
T 'Pester in Windows PowerShell' { (Get-Module -ListAvailable Pester | Sort-Object Version -Descending | Select-Object -First 3 | ForEach-Object { "Pester $($_.Version)" }) -join '; ' }
T 'python' { python --version }
T 'node / npm' { node --version; npm --version }
T 'git' { git --version }
T 'az' { (az version 2>$null | ConvertFrom-Json).'azure-cli' }
T 'bicep' { bicep --version }
T 'pac' { (pac 2>&1 | Select-Object -First 2) -join ' ' }
T 'docker' { docker version --format '{{.Server.Os}} {{.Server.Version}}' }
T 'VS Code extensions' { code --list-extensions }
T 'Visual Studio' { & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -all -format value -property displayName }
T 'Hyper-V VMs (no change)' { Get-VM | Select-Object Name, State | Format-Table -AutoSize | Out-String }
T 'Ollama / LM Studio' { ollama --version; lms version }
T 'nvidia-smi' { nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader }
$lines | Set-Content (Join-Path $out 'toolchain.txt') -Encoding utf8
Write-Host "Wrote $out\toolchain.txt" -ForegroundColor Yellow
