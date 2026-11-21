@{
    RootModule        = 'GroupsLifecycle.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000003'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft 365 groups lifecycle on Microsoft Graph: expiration policy, audit, renew, restore, archive (DEVLADLOG Microsoft 365 #3).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-GroupsLifecycleConfig', 'ConvertTo-GroupLifecyclePolicyBody', 'Compare-GroupLifecyclePolicy',
        'Get-ExpirationRolloutImpact', 'Get-GroupPurgeDate', 'Get-GroupsLifecycleFinding', 'ConvertTo-GroupsLifecycleMarkdown',
        'Invoke-GLGraphGet', 'Get-GroupsLifecycleInventory', 'Set-GroupsExpirationPolicy',
        'Invoke-GroupRenewal', 'Restore-DeletedM365Group', 'Invoke-TeamArchive'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('Microsoft365', 'Groups', 'Lifecycle', 'MicrosoftGraph') } }
}
