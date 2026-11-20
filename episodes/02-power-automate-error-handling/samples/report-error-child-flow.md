# Child flow: Report error

**Trigger:** *Manually trigger a flow* (instant) with text inputs:
`FlowName`, `Environment`, `RunUrl`, `FailedAction`, `ErrorMessage`, `BusinessKey`, `Severity`.

**Actions**
1. *Add a new row* → Flow Error Log (Dataverse).
2. *Post card in a chat or channel* (Teams) to the team's support channel, with a button that opens `RunUrl`.
3. *Respond to a Power App or flow* (required so the parent can call it as a child flow).

**Calling it:** in each parent flow's Catch scope, use *Run a Child Flow* and pass the values from the cheat sheet.

Requirements
- Parent and child flows must be in a **solution**.
- The child flow's connections must use connection references (or be set to the *embedded* connection) so it can run when called.
