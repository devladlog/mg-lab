# Demo shot list — DEVLADLOG Power Apps #10, AI Builder integration

The triage formulas, the Return check screen and the prompt text were tested locally (`dotnet test EquipmentDesk.AiBuilder.Tests -m:1` in `tests/`: 119 passed; Power Fx
interpreter 1.8.1, offline). **The model itself was never run**: the tests use a test double for `'ReturnNoteTriage'.Predict`. Everything below **needs the lab tenant** and has not been
run there: the prompt, the credits, the `.text` answer in a canvas app, the prompt in the solution. The 12 notes in `src/prompt/golden-notes.json` are the acceptance test for the prompt.

## Lab environment
No VM. Recorded on the lab Windows host: browser on the lab tenant (Power Apps, Power Platform admin center, Azure portal) and the Power Apps phone app or the browser play mode.
Credentials are never written in any file; the recorder signs in as `labadmin`.

| What | Notes | Cost |
|---|---|---|
| Lab **DEV** environment with episodes 1-9: solution **Equipment Desk** (tables, model-driven app, flow, library **Equipment Desk Kit**, canvas app **Equipment Desk (phone)** with the **Returned** button and the `returnLoan` variable from episode 7) | the canvas app must be in the solution, so the prompt can go in the same one | existing |
| **Region** of DEV | Learn: prompts are limited to some regions (see the *availability by region* pages), models differ by region and can be throttled. Check DEV's region against the page the day of the recording. An environment in a region without prompts fails the first run | 0 |
| **Credits for prompt runs in DEV: not available today.** Prompts always consume credits when run (even in preview); only tests inside the prompt builder are free. Learn (Licensing and AI Builder credits): seeded AI Builder credits (500 with Power Apps Premium) end on **1 November 2026**, new customers can't buy the AI Builder add-on and must use Copilot Credits, and with no credits the call fails (`EntitlementNotAvailable`, `QuotaExceeded`...). `series/LAB.md` says the lab's premium access is self-service trials and DEV has no pay-as-you-go plan ("not set today"); AI Builder trials are discontinued, so this is **a lab request**: | |
| ... **Pay-as-you-go billing plan for DEV** (Learn, *Set up pay-as-you-go*): Power Platform admin center > Licensing > Pay-as-you-go plans > New billing plan > Azure subscription: the lab subscription, resource group **`rg-mglab-powerapps-10`** (create it first, West Europe), the Copilot Studio product/meter (confirm the wording in the list), then pick DEV. **DEV must be a production or sandbox environment**: Learn says pay-as-you-go is available for those two types, so a Developer-type DEV can't be linked; use a sandbox environment for the recording instead | Expected: cents. One check is about 0.16 Copilot Credits by the arithmetic in the README (an estimate; I did not find the price per credit on Learn, look it up in the Azure pricing calculator before the recording). The recording needs well under 100 checks. The €30 budget `mglab-monthly` emails at 50%, 80%, 100% | pay-as-you-go, under a few euros |
| ... alternative: Copilot Credits capacity allocated to DEV | if the lab ever gets a Copilot Studio capacity pack, allocate it to DEV (admin center > Licensing > Copilot Studio). The Copilot Studio trial licences on `labadmin` and `sam.demo` let you build agents; **whether they bring credits that prompts in apps can use is not verified** (Learn says an agent trial can't publish) | 0 |
| Recording user `labadmin` (System Administrator in DEV, Power Apps Premium trial, Prompt Builder access) | the app becomes a **premium app** because it uses an AI Builder action (Learn): anyone else who runs it needs a premium licence, so only `labadmin` (and `alex.demo` after starting the premium trial) run it | existing |
| Phone with the Power Apps mobile app (optional) | the browser play mode also works; the Return check is a normal screen | free |

## Things to confirm in the lab (fix code/tests/README if they differ)
1. `'ReturnNoteTriage'.Predict(text).text` works in a canvas app as Learn's *Use your prompt in Power Apps* says, with **one positional text argument** for the one Text input. If Studio wants a
   record (`{ 'Return note': ... }`) or a different name, change `ReturnCheckScreen.pa.yaml`, the `Harness` rewrite and the tests together.
2. Output **Text** returns the JSON as a string in `.text`; and what the prompt's **JSON** output option returns in a canvas app (a record? `.structuredOutput`?). If it's a typed record, `ParseJSON`
   may no longer be needed: only then change the app.
3. Does the model add Markdown fences or chatter despite "Don't include JSON markdown in your answer"? Run the 12 golden notes 3 times each and count: the app handles fences, not chatter.
4. The default model that day (Learn's model page says GPT-4.1 mini at the basic rate; the Power Apps article still says GPT-4o mini and GPT-4o) and the temperature (default 0). The README's credit
   arithmetic assumes a basic model.
5. The **real credit use** of one check: admin center > Licensing > Copilot Studio > Environments > DEV, or Azure Cost Management on the billing plan (usage can take up to a day to show). Compare with 0.16.
6. What the error looks like with no capacity (unlink the plan for a minute off camera): the app shows the Information notification and the picker still works; note the real message.
7. Is the prompt added from **Add existing > AI models** in the solution, and does an import in another environment keep the prompt usable without a manual step? (Learn says no other step; episode 9's pipeline
   would carry it.)
8. The `{{Return note}}` marker: in the prompt builder the Text input is added with `/` or **Add content** (Learn); the file marks where it goes.

## Steps
1. **Credits (off camera).** Create the billing plan for DEV (above). Admin center > Licensing > Copilot Studio > Environments > DEV: confirm it shows pay-as-you-go.
2. **Prompt (on camera).** Power Apps > AI hub > Prompts > New custom prompt, name `ReturnNoteTriage`. Paste `src/prompt/return-note-triage.prompt.txt`; delete the `{{Return note}}` marker and add a **Text**
   input there (type `/` > Text), name it **Return note**, sample data: the first golden note. Output: **Text**. Test the 12 golden notes one by one (free): capture `prompt-screen` with the cracked-screen note,
   the missing-charger note and the injection note. Save.
3. **Solution.** Solution Equipment Desk > Add existing > AI models > ReturnNoteTriage; Managed properties > Allow customizations off (capture `solution-screen`).
4. **App.** Edit **Equipment Desk (phone)**: Data > Add data > ReturnNoteTriage. App > Formulas: add the formulas from `src/app/Src/App.pa.yaml` (from `TriageMaxChars`). Add a screen **ReturnCheckScreen** with the controls
   of `ReturnCheckScreen.pa.yaml` (or paste the YAML into Studio). On the Loans screen change **Returned**: `Set(returnLoan, ThisItem); Navigate(ReturnCheckScreen)` and remove episode 7's `dlgReturn` use for that button.
   Save and publish.
5. **Run it.** Play the app. Loan CT-0043 > Returned > type "Crack across the top right corner of the screen, still turns on and works." > **Check with AI**: the suggestion shows Damaged, the picker In repair. Mark returned
   (capture `app-screen`). Show the loan (Returned on, Notes) and the device (In repair) in the model-driven app.
6. **The unhappy paths.** Note "ok": the button stays off. A vague note ("Borrower said something was off"): the Information notification. The injection note: no suggestion for Retired; the picker offers two values.
   Optional: unlink the billing plan for a minute and show the "isn't available right now" notification, then Mark returned by hand.
7. **Credits.** Admin center > Licensing > Copilot Studio > Environments > DEV: the credits used by the session (capture `credits-screen`; it can lag, so record this a day later or show Azure Cost Management).
8. **Tests (optional capture).** Terminal: `dotnet test EquipmentDesk.AiBuilder.Tests -m:1` in `tests/`.

## Screens to capture (match `screen` scenes in script.yaml)
| Scene | File | What must be on screen |
|---|---|---|
| `prompt-screen` | `screens/prompt-builder.jpg` | Prompt builder: the instruction, the Return note Text input, model, Output Text, three golden notes answered with JSON |
| `app-screen` | `screens/return-check.jpg` | Return check on a phone or play mode: the note, the AI suggestion line, the picker on In repair, then Mark returned |
| `solution-screen` | `screens/solution-prompt.jpg` | Solution Equipment Desk with the AI model component, Add existing > AI models, Managed properties with Allow customizations off |
| `credits-screen` | `screens/credits-admin.jpg` | Admin center Licensing > Copilot Studio > Environments > DEV: pay-as-you-go plan and credits used (or the app's "isn't available right now" notification when there is no capacity) |

## Masking
- Environment names and URLs, tenant name, subscription and resource group names, user names and avatars, billing plan names. `alex.demo@contoso.com` and `CT-0043` are fictional and may stay.
- Use `pipeline/mask.js` in the browser; `series_label: "POWER APPS"` is set in `script.yaml`.

## Tear-down
1. Admin center: remove DEV from the billing plan, delete the plan. Azure portal: delete resource group `rg-mglab-powerapps-10` (the Power Platform account resource goes with it; Learn: deleting the plan
   doesn't delete the resource by itself).
2. Power Apps: delete the prompt `ReturnNoteTriage` and remove it from the solution if the lab should stay as before episode 10; revert the **Returned** button if episode 8's recording needs it.
3. Reset the demo data: CT-0043 loan open again (Returned on empty, Notes "Charger missing"), device On loan.
