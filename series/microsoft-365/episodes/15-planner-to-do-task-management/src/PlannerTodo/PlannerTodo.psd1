@{
    RootModule        = 'PlannerTodo.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000015'
    Author            = 'Momento Galatico (MG Lab)'
    CompanyName       = 'Momento Galatico'
    Copyright         = '(c) Momento Galatico (MG Lab). All rights reserved.'
    Description       = 'Planner plan from one file, plan audit and a Microsoft To Do focus list on Microsoft Graph (DEVLADLOG Microsoft 365 #15).'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-PlannerPlanConfig', 'ConvertTo-PlannerTaskBody', 'ConvertTo-PlannerDetailsBody', 'ConvertTo-PLReferenceKey', 'Get-PlannerPlanDiff',
        'Invoke-PLGraphGet', 'Invoke-PlannerPatch', 'Get-PlannerInventory', 'Set-PlannerPlan',
        'Get-PlannerFinding', 'ConvertTo-PlannerMarkdown',
        'Get-PlannerFocusTask', 'ConvertTo-TodoTaskBody', 'ConvertTo-TodoImportance', 'Sync-PlannerFocusToTodo'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
    PrivateData       = @{ PSData = @{ Tags = @('Microsoft365', 'Planner', 'ToDo', 'MicrosoftGraph') } }
}
