# PowerShell for Windows Server administration (Contoso)

Copy this file to `.github/copilot-instructions.md` in the repository that holds your admin scripts.
Instructions guide Copilot; they do not guarantee compliance, so every script still goes through review.

- Write PowerShell 7 that also runs on Windows PowerShell 5.1 unless told otherwise.
- Every script or function that changes state declares `[CmdletBinding(SupportsShouldProcess)]` and calls `$PSCmdlet.ShouldProcess()` around each change.
- Read-only tasks use `Get-*` commands only. Say so in the first comment line.
- Never use `Invoke-Expression`, `-EncodedCommand`, `-AsPlainText`, or a password or token written in the script.
- Do not pass `-Force` or `-Confirm:$false` to a command that changes state unless the prompt asks for it.
- Never target all computers: take `-ComputerName` as a parameter and default to the local server.
- Use only cmdlets that exist in the Microsoft modules on a standard Windows Server (for example Storage, NetSecurity, ServerManager, CimCmdlets). If unsure whether a cmdlet exists, say so.
- Catch errors with a message; never leave an empty `catch` block.
- Fictional names only in examples: `contoso.local`, `CON-ARC01`, `CON-SQL01`.
