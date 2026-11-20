# Dataverse table: Flow Error Log (`mgl_flowerrorlog`)

| Display name | Schema name | Type | Notes |
|---|---|---|---|
| Name | `mgl_name` | Text (primary) | `<flow name> – <failed action>` |
| Flow name | `mgl_flowname` | Text (200) | `workflow()?['tags']?['flowDisplayName']` |
| Environment | `mgl_environment` | Text (100) | `workflow()?['tags']?['environmentName']` |
| Run URL | `mgl_runurl` | URL | see cheat sheet |
| Failed action | `mgl_failedaction` | Text (200) | |
| Error message | `mgl_errormessage` | Multiline text (4000) | |
| Business key | `mgl_businesskey` | Text (200) | order number, record ID, … |
| Severity | `mgl_severity` | Choice | Info / Warning / Error / Critical |
| Occurred on | `mgl_occurredon` | Date and time | `utcNow()` |

Tips
- Put the table in the same solution as your flows; deploy it with the ALM pipeline from MG Lab #1.
- Write one row per failed run, from the **Report error** child flow, not one per successful run.
- Build a Power BI report on it: failures per flow per week, top error messages, mean time to fix.
