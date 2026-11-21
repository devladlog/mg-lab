# Demo shot list: DEVLADLOG Power Automate #6, A Teams card that gets an answer

Everything in `src/` and `tests/` already runs locally (see README). This file is for the recording session in the
**lab tenant** (DEV environment, SharePoint Online, Teams). Everything below is **needs tenant**.

## Lab environment

No VMs, no Azure resources. Recorded on the recording laptop: the Power Automate portal in a browser signed in as
`labadmin`, and Teams (web or desktop) in separate browser profiles signed in as `sam.demo`, `riley.demo` and
`alex.demo` (InPrivate windows are fine).

| What | Detail | Cost |
|---|---|---|
| Power Platform environment `DEV` (exists) | Solution, connection references, environment variables | none |
| Licences | All lab users have M365 E5 (Teams, SharePoint) and Power Apps Premium. SharePoint and Microsoft Teams are **standard** connectors: no premium licence needed | none (trials in place) |
| Teams admin center | **Workflows** app (formerly Power Automate) set to *Allowed* for the lab users (Teams admin center → Manage apps). The Teams connector's card and message actions require it | none |
| Team **IT On-call** | Owner `labadmin`; members **Sam Demo**, **Riley Demo** (on-call engineers), **Taylor Demo** (on-call lead). One **standard** channel **On-call** (not private: posting to private channels isn't supported) | none |
| SharePoint site **IT Helpdesk**, list **IT Requests** | From episode 1 (Title, Category, Priority, Status, DueDate). Add a **Person** column `AssignedTo` (internal name exactly `AssignedTo`) | none |
| Recording machine | Power Platform CLI (`pac`) and Python 3 to export, unpack and re-run the tests | none |

Users (fictional lab users from `series/LAB.md`): **Alex Demo** raises requests, **Sam Demo** and **Riley Demo**
answer cards, **Taylor Demo** is the lead who gets mentioned on timeout, `labadmin` owns the flow and both
connections (the Teams connection posts the "User" messages, so they appear from Lab Admin).

## Setup (≈ 35 min)

1. **Workflows app** allowed (see table). Sign in once to Teams as each lab user so their accounts are ready.
2. **Team and channel.** Create the team and the standard channel. Copy the team ID (groupId in *Get link to team*)
   and the channel ID (*Get link to channel*, the `19:...@thread.tacv2` part, URL-decoded). Never show them
   unmasked.
3. **List.** In IT Helpdesk → IT Requests, add `AssignedTo` (Person or Group, people only).
4. **Solution** `IT On-call` (unique name `ITOnCall`, prefix `cts`), environment variables (Text):
   `cts_HelpdeskSiteUrl` = the IT Helpdesk site URL, `cts_OnCallTeamId`, `cts_OnCallChannelId` (from step 2),
   `cts_OnCallLeadUpn` = Taylor Demo's UPN.
5. **Flow** *New → Automation → Cloud flow → Automated* `IT on-call dispatch`, trigger SharePoint *When an item is
   created* (IT Requests). Build it from `src/solution/Workflows/ITon-calldispatch-…601.json`, renaming every action
   to the JSON names:
   - Trigger condition: `@and(equals(triggerBody()?['Priority']?['Value'], 'High'), not(startsWith(coalesce(triggerBody()?['Title'], ''), '[test]')))`.
   - *Initialize variable* `dispatch` (String) = `not posted`.
   - *Compose* `Build card`: paste the card **object** from the JSON (the `Build_card` inputs), not a string.
   - Teams *Post adaptive card and wait for a response* `Ask on-call`: Post as **Flow bot**, Post in **Channel**,
     Team/Channel = the environment variables (custom value), Message = expression `string(outputs('Build_card'))`,
     Update message as in the JSON, Should update card = Yes. *Settings → Timeout* `PT30M`.
   - *Switch* `Route response` on `body('Ask_on_call')?['submitActionId']`: case `Take it` (Update item
     `Assign request` with Assigned to Claims, *Get an @mention token for a user* `Mention responder`, *Post message in a
     chat or channel* `Announce owner` as **User** in the channel, *Set variable* `Record taken`); case
     `Need more info` (*Post message in a chat or channel* `Ask requester` as Flow bot, **Chat with Flow bot**,
     Recipient = Created By Email; *Set variable*); default *Terminate* Failed `UnexpectedResponse`.
   - *Scope* `Escalate to lead`, run after `Ask on-call` **has timed out**: mention token for the lead, post as User,
     *Set variable*.
   - *Condition* `Dispatch done`, run after `Route response` and `Escalate to lead` on **is successful + is skipped**:
     `variables('dispatch')` is equal to `not posted` → *Terminate* Failed `CardNotPosted`.
6. **Export and test.**
   ```bash
   pac solution unpack --zipfile ITOnCall_1_0_0_1.zip --folder src/solution --packagetype Unmanaged --allowWrite true --allowDelete true
   python -m pytest
   ```
   Compare the exported Teams action parameters, the wait-for-response output (look at a real run's outputs:
   `submitActionId`, the responder fields, `data.note`), `item/AssignedTo/Claims`, and the @mention token text with
   the README's "What was not verified here". If they differ, keep the export, update `teamsfake` and the tests, and
   note it in the README. Replace real IDs with the zero GUIDs / `19:000...601@thread.tacv2` and the site URL with
   `https://contoso.sharepoint.com/sites/ITHelpdesk` before committing.
7. **Record the paths** (as Alex Demo, create High priority requests; each run starts after the trigger's poll,
   a few minutes):
   - "Laptop won't boot before a client demo" (Hardware, High) → Sam Demo presses **Take it**.
   - "VPN drops every 10 minutes" (Access, High) → Riley Demo types "Office or home network?" and presses **Need more
     info** → Alex sees the Workflows chat.
   - **Timeout (lab copy only):** *Save as* a copy of the flow with timeout `PT5M` (turn the original off while
     recording this path), create "Shared printer offline before payroll", don't answer for 5 minutes → Taylor Demo
     mentioned, run Succeeded. Turn the copy off afterwards.
   - Optional, to film the opening bug for real: in the copy, replace Message with the card pasted as text (README,
     first draft) and raise `Monitor 27" flickers on the left side`. Expect the post to fail. Record the **real** error
     text and put it in the README (the fake's message is its own). Restore the expression afterwards.
   - The Flow bot burst is **not** reproduced in the tenant (it would mean flooding the channel); it's a code scene
     from `python -m teamsfake burst 20`.

## Screens to capture (match `screen` scenes in `script.yaml`)

| Scene id | File | What must be on screen |
|---|---|---|
| `card` | `screens/card.jpg` | The Workflows card in IT On-call → On-call: title, facts, note box, Take it / Need more info / Open the request (as Sam Demo, before answering) |
| `taken` | `screens/taken.jpg` | The replaced card ("has been picked up") and the "@Sam Demo took high priority request #NN" message; insert: the IT Requests item with Assigned to = Sam Demo |
| `timeout` | `screens/timeout.jpg` | Run details of the PT5M copy: Ask on-call timed out, Route response skipped, Escalate to lead green, Dispatch done green, run Succeeded; insert: the channel message mentioning Taylor Demo |
| `chat` | `screens/chat.jpg` | Alex Demo's Workflows chat with Riley's note and "reply to Riley Demo" |

Code scenes (`build`, `wait`, `take`, `join`, `quote`, `budget`, `tests`) come from this folder; terminal output is
recorded locally with `python -m teamsfake quote [--first-version]` and `python -m teamsfake burst 20
[--first-version]`. After step 6, re-run them and paste the real output if it changed.

## Masking

- `pipeline/mask.js` in the browser; `series_label: "POWER AUTOMATE"`.
- Mask the tenant name, team ID, channel ID, environment ID, user object IDs in run outputs (the responder object),
  and SharePoint URLs. Only the fictional lab users (Alex, Sam, Riley, Taylor Demo, Lab Admin) on screen.
- Teams shows the tenant/org name in the title bar and profile menu: crop or mask.

## Tear-down

- Turn both flows off (original and the PT5M copy); delete the copy.
- Delete the test requests in IT Requests (or keep them for later episodes) and the test messages in the channel if
  you want a clean channel for the next recording.
- Keep the team for later episodes or delete it; reset the Workflows app policy only if you changed it just for this.
- Remove the exported zip from the recording machine after unpacking.
