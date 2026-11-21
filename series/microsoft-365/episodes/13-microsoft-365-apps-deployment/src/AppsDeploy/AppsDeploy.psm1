#Requires -Version 7.2
<#
.SYNOPSIS
    Microsoft 365 Apps deployment as code (DEVLADLOG Microsoft 365 #13).
      * One JSON file -> an Office Deployment Tool configuration.xml (install or download) AND an Intune "Microsoft 365 Apps
        for Windows 10 and later" app (officeSuiteApp, Graph beta), so both deployment routes say the same thing.
      * Validation of any configuration.xml against the values Microsoft Learn documents (also for hand-written files).
      * Install wrapper for setup.exe /configure (WhatIf-aware).
      * Client check (registry, Windows) and release check (Office release discovery API) -> findings.
      * Activation audit from the Graph report getOffice365ActivationsUserDetail.
    The analysis is pure functions, so it runs offline on saved data (and in the tests).

    Microsoft Learn sources are listed in the episode README.
#>
Set-StrictMode -Version Latest

$script:GraphBeta = '/beta'
$script:GraphV1 = '/v1.0'
$script:ReleaseApi = 'https://clients.config.office.net/releases/v1.0/filelist/channels'
$script:ZeroGuid = '00000000-0000-0000-0000-000000000000'
$script:SeverityOrder = @{ High = 3; Medium = 2; Low = 1; Info = 0 }

# ODT, Add/Updates Channel attribute: the allowed values on Learn. (PerpetualVL20xx are for volume-licensed Office 2019/2021/2024 and
# are refused here: this tool deploys the subscription product.)
$script:OdtChannels = @('BetaChannel', 'CurrentPreview', 'Current', 'MonthlyEnterprise', 'SemiAnnualPreview', 'SemiAnnual')
# ODT, ExcludeApp ID: the allowed values on Learn.
$script:OdtExcludeApps = @('Access', 'Excel', 'Groove', 'Lync', 'OneDrive', 'OneNote', 'Outlook', 'OutlookForWindows', 'PowerPoint', 'Publisher', 'Teams', 'Word')
# Intune officeSuiteApp: Learn lists exactly these productIds, and an excludedApps object with these booleans.
$script:IntuneProducts = @{ O365ProPlusRetail = 'o365ProPlusRetail'; O365BusinessRetail = 'o365BusinessRetail'; VisioProRetail = 'visioProRetail'; ProjectProRetail = 'projectProRetail' }
$script:IntuneExcluded = [ordered]@{ Access = 'access'; Groove = 'groove'; Lync = 'lync'; OneDrive = 'oneDrive'; OneNote = 'oneNote'; Outlook = 'outlook'; PowerPoint = 'powerPoint'; Publisher = 'publisher'; Teams = 'teams'; Word = 'word'; Excel = 'excel' }
$script:IntuneExcludedAll = @('access', 'bing', 'excel', 'groove', 'infoPath', 'lync', 'oneDrive', 'oneNote', 'outlook', 'powerPoint', 'publisher', 'sharePointDesigner', 'teams', 'visio', 'word')
# ODT channel -> Graph officeUpdateChannel. Taken from the alternateNames of the release discovery API (Current, Deferred = Semi-Annual,
# FirstReleaseCurrent = Current Preview, FirstReleaseDeferred = Semi-Annual Preview); MonthlyEnterprise has the same name in both.
$script:IntuneChannel = @{ Current = 'current'; CurrentPreview = 'firstReleaseCurrent'; MonthlyEnterprise = 'monthlyEnterprise'; SemiAnnual = 'deferred'; SemiAnnualPreview = 'firstReleaseDeferred' }

function Get-ADProp($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    if ($Object -is [System.Collections.IDictionary]) { if ($Object.Contains($Name)) { return $Object[$Name] } else { return $Default } }
    $p = $Object.PSObject.Properties[$Name]
    if ($p -and $null -ne $p.Value) { $p.Value } else { $Default }
}

function Test-ADLanguageId([string]$Id) {
    # Learn: examples en-us, ja-jp and the keywords MatchOS, MatchPreviousMSI, MatchInstalled.
    $Id -match '^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})+$' -or $Id -in 'MatchOS', 'MatchPreviousMSI', 'MatchInstalled'
}

# ---------------------------------------------------------------- config

function Get-ADConfig {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path $Path)) { throw "Config file not found: $Path" }
    $c = Get-Content $Path -Raw | ConvertFrom-Json
    $d = Get-ADProp $c 'deployment'
    if (-not $d) { throw "Config: 'deployment' section is missing." }

    $channel = [string](Get-ADProp $d 'channel' 'Current')
    if ($channel -match '^PerpetualVL') { throw "Config: channel '$channel' is for volume-licensed Office (LTSC / 2019); this tool deploys Microsoft 365 Apps." }
    if ($channel -notin $script:OdtChannels) { throw "Config: channel '$channel' is not one of: $($script:OdtChannels -join ', ')." }

    $edition = [string](Get-ADProp $d 'officeClientEdition' '64')
    if ($edition -notin '32', '64') { throw "Config: officeClientEdition must be '32' or '64' (Learn), got '$edition'." }

    $products = @(Get-ADProp $d 'products' @())
    if ($products.Count -eq 0) { throw 'Config: at least one product is required.' }
    foreach ($p in $products) {
        $id = [string](Get-ADProp $p 'id' '')
        if ($id -notmatch '^[A-Za-z0-9]+$') { throw "Config: product id '$id' is not valid (letters and digits, for example O365ProPlusRetail)." }
        $langs = @(Get-ADProp $p 'languages' @())
        if ($langs.Count -eq 0) { throw "Config: product '$id' needs at least one language." }
        foreach ($l in $langs) { if (-not (Test-ADLanguageId ([string]$l))) { throw "Config: language '$l' of product '$id' is not a culture code like en-us or one of MatchOS, MatchInstalled, MatchPreviousMSI." } }
        foreach ($e in @(Get-ADProp $p 'excludeApps' @())) { if ($e -notin $script:OdtExcludeApps) { throw "Config: excludeApps '$e' is not one of: $($script:OdtExcludeApps -join ', ')." } }
    }
    $level = [string](Get-ADProp $d 'displayLevel' 'Full')
    if ($level -notin 'None', 'Full') { throw "Config: displayLevel must be None or Full, got '$level'." }
    foreach ($b in 'acceptEula', 'removeMsi', 'forceAppShutdown', 'sharedComputerLicensing') {
        $v = Get-ADProp $d $b $false
        if ($v -isnot [bool]) { throw "Config: $b must be true or false." }
    }

    $a = Get-ADProp $c 'audit'
    if ($a) {
        foreach ($n in 'maxBuildsBehind', 'staleActivationDays', 'desktopActivationLimit') {
            $v = Get-ADProp $a $n
            if ($null -ne $v -and ($v -isnot [int] -and $v -isnot [long] -or $v -lt 1)) { throw "Config: audit.$n must be a whole number of 1 or more." }
        }
    }
    $c
}

# ---------------------------------------------------------------- ODT configuration.xml

function New-ADOdtXml {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute('PSUseShouldProcessForStateChangingFunctions', '', Justification = 'Builds a string in memory')]
    <# Builds configuration.xml from the config. -Mode Download omits Display/RemoveMSI/Property, which only matter at install time. #>
    [CmdletBinding()] param(
        [Parameter(Mandatory)]$Config,
        [ValidateSet('Install', 'Download')][string]$Mode = 'Install',
        [string]$SourcePath
    )
    $d = $Config.deployment
    $x = [System.Xml.XmlDocument]::new()
    $root = $x.AppendChild($x.CreateElement('Configuration'))
    $add = $root.AppendChild($x.CreateElement('Add'))
    if ($SourcePath) { $add.SetAttribute('SourcePath', $SourcePath) }
    $add.SetAttribute('OfficeClientEdition', [string](Get-ADProp $d 'officeClientEdition' '64'))
    $add.SetAttribute('Channel', [string]$d.channel)
    foreach ($p in $d.products) {
        $pe = $add.AppendChild($x.CreateElement('Product')); $pe.SetAttribute('ID', [string]$p.id)
        foreach ($l in $p.languages) { $le = $pe.AppendChild($x.CreateElement('Language')); $le.SetAttribute('ID', [string]$l) }
        foreach ($e in @(Get-ADProp $p 'excludeApps' @())) { $ee = $pe.AppendChild($x.CreateElement('ExcludeApp')); $ee.SetAttribute('ID', [string]$e) }
    }
    $u = $root.AppendChild($x.CreateElement('Updates')); $u.SetAttribute('Enabled', 'TRUE')
    if ($Mode -eq 'Install') {
        $dis = $root.AppendChild($x.CreateElement('Display'))
        $dis.SetAttribute('Level', [string](Get-ADProp $d 'displayLevel' 'Full'))
        $dis.SetAttribute('AcceptEULA', $(if (Get-ADProp $d 'acceptEula' $false) { 'TRUE' } else { 'FALSE' }))
        if (Get-ADProp $d 'removeMsi' $false) { $null = $root.AppendChild($x.CreateElement('RemoveMSI')) }
        $props = [ordered]@{ FORCEAPPSHUTDOWN = $(if (Get-ADProp $d 'forceAppShutdown' $false) { 'TRUE' } else { 'FALSE' }) }
        if (Get-ADProp $d 'sharedComputerLicensing' $false) { $props['SharedComputerLicensing'] = '1' }
        foreach ($k in $props.Keys) { $pr = $root.AppendChild($x.CreateElement('Property')); $pr.SetAttribute('Name', $k); $pr.SetAttribute('Value', $props[$k]) }
    }
    $sw = [System.IO.StringWriter]::new()
    $xw = [System.Xml.XmlTextWriter]::new($sw); $xw.Formatting = 'Indented'; $xw.Indentation = 2
    $x.WriteTo($xw); $xw.Flush()
    $sw.ToString()
}

function Test-ADOdtXml {
    <# Checks a configuration.xml (built here or by hand) against what Microsoft Learn documents. Returns a list of problems; empty = valid. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Xml)
    $problems = [System.Collections.Generic.List[string]]::new()
    try { $doc = [xml]$Xml } catch { return @("Not well-formed XML: $($_.Exception.Message)") }
    if ($doc.DocumentElement.Name -ne 'Configuration') { return @("Root element must be <Configuration>, found <$($doc.DocumentElement.Name)>.") }
    $allowedTop = 'Add', 'Remove', 'Updates', 'Display', 'RemoveMSI', 'Property', 'AppSettings', 'Logging'
    foreach ($n in $doc.DocumentElement.ChildNodes) { if ($n.NodeType -eq 'Element' -and $n.LocalName -notin $allowedTop) { $problems.Add("Unknown element <$($n.LocalName)> under <Configuration>.") } }

    foreach ($add in $doc.SelectNodes('/Configuration/Add')) {
        $ed = $add.GetAttribute('OfficeClientEdition')
        if ($add.HasAttribute('OfficeClientEdition') -and $ed -notin '32', '64') { $problems.Add("Add OfficeClientEdition must be 32 or 64, found '$ed'.") }
        $ch = $add.GetAttribute('Channel')
        if ($add.HasAttribute('Channel') -and $ch -notin $script:OdtChannels) {
            if ($ch -match '^PerpetualVL') { $problems.Add("Channel '$ch' is for volume-licensed Office, not Microsoft 365 Apps.") } else { $problems.Add("Add Channel '$ch' is not one of: $($script:OdtChannels -join ', ').") }
        }
        $ver = $add.GetAttribute('Version')
        if ($add.HasAttribute('Version') -and $ver -ne 'MatchInstalled' -and $ver -notmatch '^\d+\.\d+\.\d+\.\d+$') { $problems.Add("Add Version must be a build like 16.0.15330.20306 or MatchInstalled, found '$ver'.") }
        if ($ver -eq 'MatchInstalled' -and -not $add.HasAttribute('Channel')) { $problems.Add('Version="MatchInstalled" requires the Channel attribute (Learn).') }
        if ($add.HasAttribute('DownloadPath') -and -not $add.HasAttribute('Version')) { $problems.Add('DownloadPath requires a Version attribute (Learn).') }
        $sp = $add.GetAttribute('SourcePath')
        if ($sp -match '(?i)[\\/]Office[\\/]?$') { $problems.Add('SourcePath must not include the Office folder that holds the downloaded data (Learn).') }
        $products = @($add.SelectNodes('Product'))
        if ($products.Count -eq 0) { $problems.Add('Add has no <Product>.') }
        foreach ($p in $products) {
            $pid1 = $p.GetAttribute('ID')
            if (-not $pid1) { $problems.Add('Product without ID.') }
            $langs = @($p.SelectNodes('Language'))
            if ($langs.Count -eq 0) { $problems.Add("Product '$pid1' has no <Language>.") }
            foreach ($l in $langs) { $li = $l.GetAttribute('ID'); if (-not (Test-ADLanguageId $li)) { $problems.Add("Language ID '$li' of product '$pid1' is not a culture code or Match keyword.") } }
            foreach ($e in $p.SelectNodes('ExcludeApp')) { $ei = $e.GetAttribute('ID'); if ($ei -notin $script:OdtExcludeApps) { $problems.Add("ExcludeApp ID '$ei' is not allowed. Allowed: $($script:OdtExcludeApps -join ', ').") } }
        }
    }
    $up = $doc.SelectSingleNode('/Configuration/Updates')
    if ($up) {
        $uc = $up.GetAttribute('Channel')
        if ($up.HasAttribute('Channel') -and $uc -notin $script:OdtChannels) { $problems.Add("Updates Channel '$uc' is not one of: $($script:OdtChannels -join ', ').") }
        $en = $up.GetAttribute('Enabled'); if ($up.HasAttribute('Enabled') -and $en -notin 'TRUE', 'FALSE', 'True', 'False') { $problems.Add("Updates Enabled must be TRUE or FALSE, found '$en'.") }
    }
    $dis = $doc.SelectSingleNode('/Configuration/Display')
    if ($dis) {
        $lv = $dis.GetAttribute('Level'); if ($dis.HasAttribute('Level') -and $lv -notin 'None', 'Full') { $problems.Add("Display Level must be None or Full, found '$lv'.") }
        $ae = $dis.GetAttribute('AcceptEULA'); if ($dis.HasAttribute('AcceptEULA') -and $ae -notin 'TRUE', 'FALSE', 'True', 'False') { $problems.Add("Display AcceptEULA must be TRUE or FALSE, found '$ae'.") }
    }
    foreach ($pr in $doc.SelectNodes('/Configuration/Property')) {
        $name = $pr.GetAttribute('Name'); $val = $pr.GetAttribute('Value')
        switch ($name) {
            { $_ -in 'SharedComputerLicensing', 'SCLCacheOverride', 'DeviceBasedLicensing', 'AUTOACTIVATE' } { if ($val -notin '0', '1') { $problems.Add("Property $name must be 0 or 1, found '$val'.") } }
            { $_ -in 'FORCEAPPSHUTDOWN', 'PinIconsToTaskbar' } { if ($val -notin 'TRUE', 'FALSE', 'True', 'False') { $problems.Add("Property $name must be TRUE or FALSE, found '$val'.") } }
        }
        if ($name -eq 'AUTOACTIVATE' -and $val -eq '1') { $problems.Add('AUTOACTIVATE should not be set for Microsoft 365 Apps products: they activate automatically (Learn).') }
    }
    @($problems)
}

function Install-ADOffice {
    <# Runs the Office Deployment Tool: setup.exe /configure <file> (or /download). Needs local administrator on the client. #>
    [CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')] param(
        [Parameter(Mandatory)]$Config,
        [Parameter(Mandatory)][string]$OdtPath,
        [ValidateSet('Install', 'Download')][string]$Mode = 'Install',
        [string]$SourcePath,
        [string]$WorkDir = ([System.IO.Path]::GetTempPath())
    )
    if (-not (Test-Path $OdtPath)) { throw "Office Deployment Tool not found at $OdtPath. Download it from the Microsoft Download Center (link in the README) and pass the path to setup.exe." }
    $xml = New-ADOdtXml -Config $Config -Mode $Mode -SourcePath $SourcePath
    $bad = @(Test-ADOdtXml -Xml $xml)
    if ($bad.Count) { throw "Generated configuration is invalid: $($bad -join ' ')" }
    $file = Join-Path $WorkDir ("odt-{0}-{1}.xml" -f $Mode.ToLower(), [guid]::NewGuid().ToString('N').Substring(0, 8))
    Set-Content -Path $file -Value $xml -Encoding utf8 -WhatIf:$false   # the temp file is harmless: -WhatIf must still leave the file to inspect
    $switch = if ($Mode -eq 'Download') { '/download' } else { '/configure' }
    $plan = [pscustomobject]@{ Mode = $Mode; Command = "$OdtPath $switch $file"; ConfigFile = $file }
    if ($PSCmdlet.ShouldProcess($env:COMPUTERNAME, "$OdtPath $switch $file")) {
        & $OdtPath $switch $file
        $code = $LASTEXITCODE
        if ($code -ne 0) { throw "setup.exe $switch exited with code $code. Read the log files in the %temp% folder (Learn)." }
        $plan | Add-Member Result 'Done' -PassThru
    } else { $plan | Add-Member Result 'WhatIf' -PassThru }
}

# ---------------------------------------------------------------- Intune officeSuiteApp (Graph beta)

function ConvertTo-ADOfficeSuiteAppBody {
    [CmdletBinding()] param([Parameter(Mandatory)]$Config)
    $d = $Config.deployment; $i = Get-ADProp $Config 'intune'
    if (-not $i) { throw "Config: 'intune' section is missing." }
    if (-not (Get-ADProp $i 'displayName')) { throw 'Config: intune.displayName is required.' }
    $ids = [System.Collections.Generic.List[string]]::new()
    $excluded = [ordered]@{ '@odata.type' = 'microsoft.graph.excludedApps' }
    foreach ($k in $script:IntuneExcludedAll) { $excluded[$k] = $false }
    foreach ($p in $d.products) {
        if (-not $script:IntuneProducts.ContainsKey([string]$p.id)) { throw "Intune supports only these product ids (Learn): $($script:IntuneProducts.Keys -join ', '). Got '$($p.id)'." }
        $ids.Add($script:IntuneProducts[[string]$p.id])
        foreach ($e in @(Get-ADProp $p 'excludeApps' @())) {
            if (-not $script:IntuneExcluded.Contains($e)) { throw "excludeApps '$e' has no property in the Graph excludedApps type (Learn lists: $($script:IntuneExcludedAll -join ', '))." }
            $excluded[$script:IntuneExcluded[$e]] = $true
        }
    }
    $langs = @($d.products | ForEach-Object { $_.languages } | Select-Object -Unique)
    foreach ($l in $langs) { if ($l -in 'MatchOS', 'MatchInstalled', 'MatchPreviousMSI') { throw "Language '$l' is an ODT keyword; the Intune app takes culture codes only (localesToInstall)." } }
    $ch = [string]$d.channel
    if (-not $script:IntuneChannel.ContainsKey($ch)) { throw "Update channel '$ch' has no Graph officeUpdateChannel value (known: $($script:IntuneChannel.Keys -join ', '))." }
    $arch = if ((Get-ADProp $d 'officeClientEdition' '64') -eq '32') { 'x86' } else { 'x64' }
    [ordered]@{
        '@odata.type'                        = '#microsoft.graph.officeSuiteApp'
        displayName                          = [string]$i.displayName
        description                          = [string](Get-ADProp $i 'description' '')
        publisher                            = [string](Get-ADProp $i 'publisher' 'Microsoft')
        autoAcceptEula                       = [bool](Get-ADProp $d 'acceptEula' $false)
        productIds                           = @($ids)
        excludedApps                         = $excluded
        useSharedComputerActivation          = [bool](Get-ADProp $d 'sharedComputerLicensing' $false)
        updateChannel                        = $script:IntuneChannel[$ch]
        officePlatformArchitecture           = $arch
        localesToInstall                     = @($langs)
        installProgressDisplayLevel          = ([string](Get-ADProp $d 'displayLevel' 'Full')).ToLowerInvariant()
        shouldUninstallOlderVersionsOfOffice = [bool](Get-ADProp $d 'removeMsi' $false)
    }
}

function Invoke-ADGraph {
    [CmdletBinding()] param([string]$Method = 'GET', [Parameter(Mandatory)][string]$Uri, $Body)
    $p = @{ Method = $Method; Uri = $Uri; ErrorAction = 'Stop' }
    if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Depth 10); $p.ContentType = 'application/json' }
    Invoke-MgGraphRequest @p
}

function Get-ADOfficeSuiteApp {
    <# All mobileApps are paged and filtered client-side: Learn's list page documents GET /mobileApps without a $filter. #>
    [CmdletBinding()] param()
    $uri = "$script:GraphBeta/deviceAppManagement/mobileApps"
    while ($uri) {
        $r = Invoke-ADGraph -Uri $uri
        foreach ($a in @(Get-ADProp $r 'value' @())) { if ((Get-ADProp $a '@odata.type') -eq '#microsoft.graph.officeSuiteApp') { $a } }
        $uri = Get-ADProp $r '@odata.nextLink'
    }
}

function Compare-ADOfficeSuiteApp {
    <# Which properties of the desired body differ from the app in the tenant? Returns property names. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Desired, [Parameter(Mandatory)]$Existing)
    $diff = [System.Collections.Generic.List[string]]::new()
    foreach ($k in $Desired.Keys) {
        if ($k -eq '@odata.type') { continue }
        $want = $Desired[$k]; $have = Get-ADProp $Existing $k
        if ($k -eq 'excludedApps') {
            foreach ($f in $script:IntuneExcludedAll) { if ([bool](Get-ADProp $have $f $false) -ne [bool]$want[$f]) { $diff.Add("excludedApps.$f") } }
        } elseif ($want -is [array]) {
            if ((@($want | Sort-Object) -join '|') -ne (@(@($have) | Sort-Object) -join '|')) { $diff.Add($k) }
        } elseif ("$want" -ne "$have") { $diff.Add($k) }
    }
    @($diff)
}

function Set-ADOfficeSuiteApp {
    <# Creates the app, or PATCHes it when properties differ; then (re)assigns it to the group in config. Honors -WhatIf. #>
    [CmdletBinding(SupportsShouldProcess)] param([Parameter(Mandatory)]$Config)
    $body = ConvertTo-ADOfficeSuiteAppBody -Config $Config
    $assign = Get-ADProp (Get-ADProp $Config 'intune') 'assignTo'
    $group = [string](Get-ADProp $assign 'groupId' '')
    $intent = [string](Get-ADProp $assign 'intent' 'required')
    $wantAssign = [bool]$group
    if ($group) {
        $g = [guid]::Empty
        if (-not [guid]::TryParse($group, [ref]$g)) { throw "assignTo.groupId '$group' is not a GUID." }
        if ($group -eq $script:ZeroGuid) { throw 'assignTo.groupId is still the zero GUID placeholder: put the Object Id of the Entra group in your local copy of the config.' }
        if ($intent -notin 'available', 'required', 'uninstall', 'availableWithoutEnrollment') { throw "assignTo.intent '$intent' is not a mobileAppIntent value." }
    }
    $existing = @(Get-ADOfficeSuiteApp | Where-Object { $_.displayName -eq $body.displayName })
    if ($existing.Count -gt 1) { throw "More than one Microsoft 365 Apps app is called '$($body.displayName)'; rename or delete the duplicates first." }
    $changes = @(); $row = [ordered]@{ Name = $body.displayName; Action = ''; Changes = ''; Id = '' }
    if ($existing.Count -eq 0) {
        $row.Action = 'Create'
        if ($PSCmdlet.ShouldProcess($body.displayName, 'POST officeSuiteApp')) {
            $created = Invoke-ADGraph -Method POST -Uri "$script:GraphBeta/deviceAppManagement/mobileApps" -Body $body
            $row.Id = [string](Get-ADProp $created 'id'); $row.Action = 'Created'; $existingId = $row.Id
        } else { $row.Action = 'WhatIf-Create'; $existingId = $null }
        $changes = @('new app')
    } else {
        $existingId = [string]$existing[0].id; $row.Id = $existingId
        $changes = @(Compare-ADOfficeSuiteApp -Desired $body -Existing $existing[0])
        if ($changes.Count) {
            $row.Action = 'Update'
            if ($PSCmdlet.ShouldProcess($body.displayName, "PATCH officeSuiteApp ($($changes -join ', '))")) {
                $null = Invoke-ADGraph -Method PATCH -Uri "$script:GraphBeta/deviceAppManagement/mobileApps/$existingId" -Body $body
                $row.Action = 'Updated'
            } else { $row.Action = 'WhatIf-Update' }
        } else { $row.Action = 'Unchanged' }
    }
    $row.Changes = $changes -join ', '
    if ($wantAssign -and $existingId -and $row.Action -in 'Created', 'Updated', 'Unchanged') {
        $assignBody = @{ mobileAppAssignments = @(@{
                    '@odata.type' = '#microsoft.graph.mobileAppAssignment'
                    intent        = $intent
                    target        = @{ '@odata.type' = '#microsoft.graph.groupAssignmentTarget'; groupId = $group }
                }) }
        if ($PSCmdlet.ShouldProcess($body.displayName, "assign to group ($intent)")) {
            $null = Invoke-ADGraph -Method POST -Uri "$script:GraphBeta/deviceAppManagement/mobileApps/$existingId/assign" -Body $assignBody
            $row.Changes = (@($row.Changes, "assigned ($intent)") | Where-Object { $_ }) -join ', '
        }
    }
    [pscustomobject]$row
}

# ---------------------------------------------------------------- client check (registry) and release discovery

function Get-ADReleaseChannel {
    <# The Office release discovery API (no permissions needed, Learn): channels, their CDN base URL, and the latest builds. #>
    [CmdletBinding()] param([string]$Path)
    if ($Path) { return @((Get-Content $Path -Raw | ConvertFrom-Json)) | ForEach-Object { $_ } }
    Invoke-RestMethod -Uri $script:ReleaseApi -ErrorAction Stop | ForEach-Object { $_ }
}

function Resolve-ADChannel {
    <# Maps a CDNBaseUrl/UpdateChannel registry value (http://officecdn.microsoft.com/pr/<guid>) to a channel by its GUID. #>
    [CmdletBinding()] param([string]$Url, [Parameter(Mandatory)][object[]]$Releases)
    if (-not $Url) { return $null }
    $m = [regex]::Match($Url, '[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}')
    if (-not $m.Success) { return $null }
    $Releases | Where-Object { $_.baseUrl -match [regex]::Escape($m.Value) } | Select-Object -First 1
}

function Read-ADRegistryValue {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Name)
    $item = Get-ItemProperty -Path $Path -Name $Name -ErrorAction SilentlyContinue
    if ($item) { $item.$Name } else { $null }
}

function Get-ADOfficeClient {
    <# Reads this Windows PC. Version and product come from the Click-to-Run Inventory key, as Microsoft's guidance says
       (VersionToReport is telemetry, not an installation-state contract). #>
    [CmdletBinding()] param()
    if (-not $IsWindows) { throw 'Get-ADOfficeClient reads the Windows registry; run it on the Windows client.' }
    $c2r = 'HKLM:\SOFTWARE\Microsoft\Office\ClickToRun'
    $store = $null
    if (Get-Command Get-AppxPackage -ErrorAction SilentlyContinue) { $store = Get-AppxPackage -Name Microsoft.Office.Desktop -ErrorAction SilentlyContinue }
    [pscustomobject]@{
        ComputerName    = $env:COMPUTERNAME
        PackageVersion  = [string](Read-ADRegistryValue "$c2r\Inventory\Office\16.0" 'OfficePackageVersion')
        ProductIds      = [string](Read-ADRegistryValue "$c2r\Inventory\Office\16.0" 'OfficeProductReleaseIds')
        Architecture    = [string](Read-ADRegistryValue "$c2r\Inventory\Office" 'OfficePackageArchitecture')
        CdnBaseUrl      = [string](Read-ADRegistryValue "$c2r\Configuration" 'CDNBaseUrl')
        UpdateChannel   = [string](Read-ADRegistryValue "$c2r\Configuration" 'UpdateChannel')
        StoreInstallType = [bool]$store
    }
}

function Get-ADClientFinding {
    [CmdletBinding()] param(
        [Parameter(Mandatory)]$Client,
        [Parameter(Mandatory)]$Config,
        [Parameter(Mandatory)][object[]]$Releases
    )
    $findings = [System.Collections.Generic.List[object]]::new()
    function Add-F($Sev, $Type, $Detail) { $findings.Add([pscustomobject]@{ Severity = $Sev; Type = $Type; Computer = $Client.ComputerName; Detail = $Detail }) }
    $audit = Get-ADProp $Config 'audit'
    $maxBehind = [int](Get-ADProp $audit 'maxBuildsBehind' 2)

    if ($Client.StoreInstallType) {
        Add-F 'High' 'StoreInstallType' 'The Microsoft Store installation type is present. Learn: feature updates stopped in October 2025 and security updates end in December 2026. Deploy the Click-to-Run installation with the ODT or Intune (it detects and removes the Store type).'
    }
    if (-not $Client.PackageVersion) {
        Add-F 'High' 'NotInstalled' 'No Click-to-Run Microsoft 365 Apps found in HKLM\SOFTWARE\Microsoft\Office\ClickToRun\Inventory\Office\16.0.'
        return @($findings)
    }
    foreach ($id in @($Config.deployment.products | ForEach-Object { $_.id })) {
        if (($Client.ProductIds -split '[,\s]+') -notcontains $id) { Add-F 'High' 'ProductMissing' "Expected product $id is not in OfficeProductReleaseIds ('$($Client.ProductIds)')." }
    }
    $wantArch = if ((Get-ADProp $Config.deployment 'officeClientEdition' '64') -eq '32') { 'x86' } else { 'x64' }
    if ($Client.Architecture -and $Client.Architecture -ne $wantArch) { Add-F 'Medium' 'ArchitectureMismatch' "Installed $($Client.Architecture), config says $wantArch. Switching needs MigrateArch=TRUE in the ODT (Learn); mixed architectures are not supported." }

    $url = if ($Client.UpdateChannel) { $Client.UpdateChannel } else { $Client.CdnBaseUrl }
    $channel = Resolve-ADChannel -Url $url -Releases $Releases
    if (-not $channel) {
        Add-F 'Low' 'UnknownChannel' "The channel URL '$url' matches no channel in the release discovery data (a Beta Channel build, a private source or a newer channel?)."
        return @($findings)
    }
    if ($channel.name -ne $Config.deployment.channel) {
        $note = if ($channel.name -eq 'SemiAnnual' -and $Config.deployment.channel -eq 'MonthlyEnterprise') { ' Learn: since Version 2606, Semi-Annual Enterprise devices receive the Monthly Enterprise Channel updates and some tools keep reporting the old name; check the build before treating this as drift.' } else { '' }
        Add-F 'Medium' 'ChannelMismatch' "Running $($channel.name) ($($channel.displayName)); the config wants $($Config.deployment.channel).$note"
    }
    # How far behind the channel's published builds is this device?
    $have = [version]$Client.PackageVersion
    $builds = @($channel.updates | ForEach-Object { [version]$_.legacyVersion })
    $idx = [array]::IndexOf($builds, $have)
    if ($idx -ge $maxBehind) { Add-F 'Medium' 'BuildBehind' "Build $($Client.PackageVersion) is $idx releases behind $($channel.latestUpdateVersion) on $($channel.name)." }
    elseif ($idx -lt 0) {
        if ($builds.Count -and $have -lt ($builds | Measure-Object -Minimum).Minimum) { Add-F 'Medium' 'BuildBehind' "Build $($Client.PackageVersion) is older than the $($builds.Count) most recent $($channel.name) builds; latest is $($channel.latestUpdateVersion)." }
        elseif ($builds.Count -and $have -gt ($builds | Measure-Object -Maximum).Maximum) { Add-F 'Low' 'BuildAhead' "Build $($Client.PackageVersion) is newer than the latest published on $($channel.name) ($($channel.latestUpdateVersion))." }
        else { Add-F 'Low' 'BuildNotListed' "Build $($Client.PackageVersion) is not in the published list of $($channel.name)." }
    }
    @($findings | Sort-Object { -$script:SeverityOrder[$_.Severity] }, Type)
}

# ---------------------------------------------------------------- activation audit (Graph report)

function Get-ADActivationReport {
    <# GET /reports/getOffice365ActivationsUserDetail (Reports.Read.All). The API answers 302 to a CSV; -OutputFilePath saves it. #>
    [CmdletBinding()] param([string]$Path)
    if ($Path) { return @(Import-Csv $Path) }
    $tmp = New-TemporaryFile
    try {
        Invoke-MgGraphRequest -Method GET -Uri "$script:GraphV1/reports/getOffice365ActivationsUserDetail" -OutputFilePath $tmp.FullName -ErrorAction Stop
        @(Import-Csv $tmp.FullName)
    } finally { Remove-Item $tmp.FullName -ErrorAction SilentlyContinue }
}

function ConvertTo-ADCount($Value) { $n = 0; if ([int]::TryParse("$Value", [ref]$n)) { $n } else { 0 } }

function Get-ADActivationFinding {
    [CmdletBinding()] param([Parameter(Mandatory)][object[]]$Rows, [Parameter(Mandatory)]$Config, [datetimeoffset]$Now = [datetimeoffset]::UtcNow)
    $audit = Get-ADProp $Config 'audit'
    $limit = [int](Get-ADProp $audit 'desktopActivationLimit' 5)
    $stale = [int](Get-ADProp $audit 'staleActivationDays' 90)
    foreach ($r in $Rows) {
        $upn = $r.'User Principal Name'; $win = ConvertTo-ADCount $r.Windows; $mac = ConvertTo-ADCount $r.Mac
        $mobile = (ConvertTo-ADCount $r.iOS) + (ConvertTo-ADCount $r.Android) + (ConvertTo-ADCount $r.'Windows 10 Mobile')
        $shared = "$($r.'Activated On Shared Computer')" -in 'Yes', 'True', '1', 'TRUE'
        $f = { param($s, $t, $d) [pscustomobject]@{ Severity = $s; Type = $t; User = $upn; Product = $r.'Product Type'; Detail = $d } }
        if (-not $shared -and ($win + $mac) -ge $limit) { & $f 'Medium' 'DesktopAtLimit' "$win Windows + $mac Mac activations. Learn: a licence covers up to $limit desktops; past 10 devices the least recently used one is deactivated automatically." }
        $last = [datetimeoffset]::MinValue
        if ($r.'Last Activated Date' -and [datetimeoffset]::TryParse($r.'Last Activated Date', [cultureinfo]::InvariantCulture, 'AssumeUniversal', [ref]$last)) {
            $age = [int]($Now - $last).TotalDays
            if ($age -gt $stale) { & $f 'Low' 'StaleActivation' "Last activated $age days ago (limit $stale). Licensed but not using the desktop apps, or a leaver whose licence is still assigned." }
        }
        if (($win + $mac) -eq 0 -and $mobile -gt 0 -and -not $shared) { & $f 'Info' 'MobileOnly' "$mobile mobile activation(s) and no desktop activation." }
        if ($shared) { & $f 'Info' 'SharedComputer' 'Activated on a shared computer (shared computer activation does not count against the desktop limit).' }
    }
}

# ---------------------------------------------------------------- output

function ConvertTo-ADMarkdown {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Title, [object[]]$Findings = @(), [string]$Asof = '', [string[]]$Notes = @())
    $sb = [System.Text.StringBuilder]::new()
    $null = $sb.AppendLine("# $Title"); $null = $sb.AppendLine()
    if ($Asof) { $null = $sb.AppendLine("_As of $Asof._"); $null = $sb.AppendLine() }
    foreach ($n in $Notes) { $null = $sb.AppendLine($n) }
    if ($Notes) { $null = $sb.AppendLine() }
    $sorted = @($Findings | Sort-Object { -$script:SeverityOrder[$_.Severity] }, Type)
    $null = $sb.AppendLine("**$($sorted.Count) finding(s):** " + ((@('High', 'Medium', 'Low', 'Info') | ForEach-Object { "$(@($sorted | Where-Object Severity -eq $_).Count) $_" }) -join ' / '))
    $null = $sb.AppendLine()
    if ($sorted.Count) {
        $null = $sb.AppendLine('| Severity | Type | Who | Detail |'); $null = $sb.AppendLine('|---|---|---|---|')
        foreach ($f in $sorted) {
            $who = if ($f.PSObject.Properties['User']) { $f.User } else { $f.Computer }
            $null = $sb.AppendLine("| $($f.Severity) | $($f.Type) | $who | $(([string]$f.Detail) -replace '\|', '/') |")
        }
    }
    $sb.ToString()
}

Export-ModuleMember -Function Get-ADConfig, New-ADOdtXml, Test-ADOdtXml, Install-ADOffice, ConvertTo-ADOfficeSuiteAppBody, Get-ADOfficeSuiteApp,
    Compare-ADOfficeSuiteApp, Set-ADOfficeSuiteApp, Get-ADReleaseChannel, Resolve-ADChannel, Get-ADOfficeClient, Get-ADClientFinding,
    Get-ADActivationReport, Get-ADActivationFinding, ConvertTo-ADMarkdown
