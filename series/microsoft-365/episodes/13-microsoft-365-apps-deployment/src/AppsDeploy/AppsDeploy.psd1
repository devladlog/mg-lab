@{
    RootModule        = 'AppsDeploy.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000013'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft 365 Apps deployment as code: one JSON file to an Office Deployment Tool configuration.xml and an Intune officeSuiteApp, an install wrapper, client and release checks, and an activation audit (DEVLADLOG Microsoft 365 #13).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-ADConfig', 'New-ADOdtXml', 'Test-ADOdtXml', 'Install-ADOffice', 'ConvertTo-ADOfficeSuiteAppBody', 'Get-ADOfficeSuiteApp',
        'Compare-ADOfficeSuiteApp', 'Set-ADOfficeSuiteApp', 'Get-ADReleaseChannel', 'Resolve-ADChannel', 'Get-ADOfficeClient', 'Get-ADClientFinding',
        'Get-ADActivationReport', 'Get-ADActivationFinding', 'ConvertTo-ADMarkdown'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('Microsoft365Apps', 'OfficeDeploymentTool', 'Intune', 'MicrosoftGraph') } }
}
