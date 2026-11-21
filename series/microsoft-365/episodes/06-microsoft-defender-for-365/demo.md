# Demo shot list — DEVLADLOG Microsoft 365 #6: Microsoft Defender for Office 365

Everything in `src/` and `tests/` already ran in the build container (48 Pester tests with the real
ExchangeOnlineManagement and Microsoft.Graph.Authentication modules and the Kusto.Language KQL check; offline audit,
hunting queries and simulation summary from fixtures). This file lists what the human-supervised session must set up
and record in the **lab tenant**. Every Exchange Online and Graph call below is **needs tenant**.

**Safety:** no real malware and no real phishing, ever. Malware = the **EICAR** test file, sent **internally**
(Alex → Sam), as Microsoft documents for testing anti-malware policies. Phishing = **Attack simulation training** with
a **Microsoft-provided payload** against lab users only. Nothing is sent outside the tenant.

## Lab environment

No VMs and no Azure resources. Lab tenant (Microsoft 365 E5 trial, includes Defender for Office 365 Plan 2, ends
20 Dec 2026), recording laptop (PowerShell 7 + browser). Cost: none beyond the existing trial.

| Item | Notes | Cost |
|---|---|---|
| Microsoft 365 E5 trial | Built-in protection features + Defender for Office 365 Plan 2 (Safe Links, Safe Attachments, Attack simulation training, hunting) | in the lab |
| Recording account `labadmin` | **Security Administrator** covers preset policies and Attack simulation training; reading recipients/groups needs Exchange read access (the lab's admin account has it) | none |
| Lab users | `alex.demo`, `sam.demo`, `jordan.demo`, `riley.demo`, `taylor.demo` (mailboxes, E5) | none |
| Groups (created in setup) | **Priority Accounts** (`priority-accounts@<lab domain>`, mail-enabled security group: labadmin, riley.demo) and **All Staff** (`all-staff@<lab domain>`, mail-enabled security group: labadmin, alex.demo, sam.demo, riley.demo — Jordan and Taylor deliberately left out) | none |
| PowerShell 7.2+ | `Install-Module ExchangeOnlineManagement, Microsoft.Graph.Authentication -Scope CurrentUser` | none |
| Delegated Graph consent | `ThreatHunting.Read.All`, `AttackSimulation.Read.All` (the runner calls `Connect-MgGraph -Scopes …`) | none |
| Recording laptop antivirus | A folder **excluded from scanning** for `EICAR.TXT` (Learn: exclude it, or the local antivirus quarantines it) | none |
| Browser with `pipeline/mask.js` | Defender portal as Lab Admin; second profile as Alex, third as Sam | none |

## Setup (before recording)

1. Copy `src/defender.json` to an uncommitted `src/defender.lab.json`; replace `contoso.onmicrosoft.com` (domain and
   the Priority Accounts address). Pass `-PolicyFile ./defender.lab.json` everywhere below.
2. Exchange admin center → Recipients → Groups → **Mail-enabled security**: create *Priority Accounts* and *All Staff*
   with the members above (or `New-DistributionGroup -Type Security`).
3. **Turn on the presets once in the portal** — the Standard/Strict rules don't exist until you do (Learn).
   Defender portal → Email & collaboration → Policies & rules → Threat policies → **Preset security policies**:
   - *Standard protection* → Manage protection settings → EOP and Defender for Office 365 recipients: **Domains** = lab
     domain **and** **Groups** = All Staff (this is the trap for screen 1) → no impersonation entries → turn on.
   - *Strict protection* → Groups = Priority Accounts → turn on.
   - Then turn off the Defender half of Strict: `Disable-ATPProtectionPolicyRule -Identity "Strict Preset Security Policy"`.
   Allow some time for the changes to apply before recording.
4. Offline check on the recording laptop: `dotnet build -c Release tests/kql` then
   `pwsh -NoProfile -Command 'Invoke-Pester ./tests'` → 48 passed (with both modules installed).
5. Terminal: dark theme, font 18+, prompt `PS> `.

## Screens to capture (match the `screen` scenes in script.yaml)

### 1. `screens/audit-before.jpg` — "The audit finds the trap" (**needs tenant**, read-only)
```powershell
cd src
Connect-ExchangeOnline -UserPrincipalName <labadmin UPN>
./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -Audit -SaveInventory ./inventory.lab.json
```
Expected coverage: jordan.demo and taylor.demo `Default/custom` + `Built-in protection`; labadmin and riley.demo
`Strict` (EOP) + `Standard` (Defender). Findings: `PresetDisabled` (ATP Strict), `CombinedConditions` naming Jordan
and Taylor, `PriorityNotStrict` ×2, `NotOnPreset` ×2, `Drift`, plus whatever `BelowStandard` rows the configuration
analyzer returns for the lab's default/custom policies. Rewrite the narration to the real output.
**Verify and note in README**: that rule objects expose `State`, `SentTo`, `SentToMemberOf`, `RecipientDomainIs`
(and the `ExceptIf…` twins) as the module reads them, and whether `SentToMemberOf` comes back as the address or the
display name of the group (the coverage lookup queries members with exactly that value).

### 2. `screens/apply.jpg` — "Apply the file, audit again" (**needs tenant**, changes who is protected)
```powershell
./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -ApplyPresets -WhatIf
./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -ApplyPresets        # confirm
./Invoke-DefenderForOffice.ps1 -PolicyFile ./defender.lab.json -Audit
```
Expected: 4 × `WhatIf`, then 4 × `Applied` (the Strict ATP rule gets enabled). Second audit: every mailbox
`Standard` or `Strict` for both columns, labadmin and riley `Strict`/`Strict`; only `BelowStandard` findings remain.
Then the portal page **Preset security policies**: Standard and Strict both on, recipients as in the file.

### 3. `screens/eicar.jpg` — "EICAR, inside the tenant" (**needs tenant**)
1. In the excluded folder, Notepad → paste exactly `X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*`
   → save as `EICAR.TXT` (68 bytes).
2. As **Alex** in Outlook on the web: new message **to sam.demo** (internal), subject "Test attachment", attach
   `EICAR.TXT`, send. As **Sam**: the message isn't in the inbox.
3. When it shows up in hunting (can take a while):
```powershell
Connect-MgGraph -Scopes ThreatHunting.Read.All -NoWelcome
./Invoke-DefenderForOffice.ps1 -Hunt -Recipient sam.demo@<lab domain> -Days 1
./Invoke-DefenderForOffice.ps1 -Hunt -Days 1
```
Expected: Sam's message with a `Malware` threat type, blocked, quarantined (the module prints whatever
`ThreatTypes`/`DeliveryAction`/`DeliveryLocation` the service returns — rewrite narration to those values). Optional:
Defender portal → Email & collaboration → Review → Quarantine shows the message. **Delete `EICAR.TXT`** afterwards.

### 4. `screens/simulation.jpg` — "A phishing simulation, safely" (**needs tenant**)
1. Defender portal → Email & collaboration → **Attack simulation training** → Simulations → **Launch a simulation**:
   technique *Credential Harvest*, a **Microsoft-provided (global) payload**, target users alex.demo, sam.demo,
   jordan.demo, taylor.demo, assign the recommended training, launch now, short duration.
2. As **Alex**: open the simulation message, click the link, type a made-up password on the simulated page (never a
   real one). As **Sam**: Report → Report phishing. Jordan and Taylor do nothing.
3. When the simulation shows results:
```powershell
Connect-MgGraph -Scopes AttackSimulation.Read.All -NoWelcome
./Invoke-DefenderForOffice.ps1 -SimulationReport            # most recent simulation, or -SimulationId <id>
```
Expected: Targeted 4, Compromised 1, Reported 1, per-user table with training counts; with 25% compromised the
`CompromiseRateHigh` finding (target 20%) appears. Rewrite narration numbers to match. Capture the portal's
simulation report next to the PowerShell output.

## Masking checklist
- Tenant name/domain, admin UPN, user addresses beyond the lab aliases, simulation and message IDs.
- `inventory.lab.json` contains the lab's mailbox list: don't show it in full.

## Tear-down (before the trial ends on 20 Dec 2026)
1. Presets: keep them (they're Microsoft's recommended settings) or turn them off:
   `Disable-EOPProtectionPolicyRule` / `Disable-ATPProtectionPolicyRule` for "Standard Preset Security Policy" and
   "Strict Preset Security Policy" (turning off doesn't delete the rules).
2. Release or delete the quarantined EICAR message (Quarantine page); delete `EICAR.TXT` from the laptop.
3. Attack simulation training: let the simulation complete; remove the assigned training if you don't want reminders.
4. Delete the *All Staff* group (only made for the trap); keep *Priority Accounts* if later episodes use it.
5. Delete `defender.lab.json`, `inventory.lab.json`; `Disconnect-ExchangeOnline`; `Disconnect-MgGraph`; remove the
   delegated consent granted only for the recording.
