@{
    RootModule        = 'IdentityGovernance.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000004'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Microsoft Entra ID Governance as code on Microsoft Graph: PIM eligibility, guest access reviews, leaver lifecycle workflow, audit (DEVLADLOG Microsoft 365 #4).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-IdentityGovernanceConfig', 'New-PimEligibilityRequest', 'New-GuestAccessReviewDefinition', 'New-LeaverWorkflowDefinition',
        'Get-GuestBillingTrigger', 'Get-LeaverPreflight', 'Get-IdentityGovernanceFinding', 'ConvertTo-IdentityGovernanceMarkdown',
        'Invoke-IGGraphGet', 'Get-IdentityGovernanceInventory', 'New-PimEligibleAssignment', 'New-GuestAccessReview',
        'New-LeaverWorkflow', 'Invoke-LeaverWorkflow'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('EntraID', 'IdentityGovernance', 'PIM', 'AccessReviews', 'LifecycleWorkflows', 'MicrosoftGraph') } }
}
