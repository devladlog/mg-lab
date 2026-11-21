@{
    RootModule        = 'ExchangeAdmin.psm1'
    ModuleVersion     = '1.0.0'
    GUID              = '00000000-0000-0000-0000-000000000010'
    Author            = 'DEVLADLOG'
    Description       = 'Exchange Online administration: read-only audit of mail forwarding, shared mailboxes and transport rules; guarded fixes with rollback; declarative shared mailboxes; message trace.'
    PowerShellVersion = '7.2'
    FunctionsToExport = @(
        'Get-EAConfig', 'Get-EAInventory', 'Get-EAFinding', 'Get-EASummary', 'ConvertTo-EAMarkdown',
        'Get-EAFixPlan', 'Invoke-EAForwardingFix', 'Restore-EAForwarding',
        'Get-EASharedMailboxPlan', 'Invoke-EASharedMailboxPlan', 'Get-EAMessageTrace'
    )
    CmdletsToExport   = @()
    VariablesToExport = @()
    AliasesToExport   = @()
}
