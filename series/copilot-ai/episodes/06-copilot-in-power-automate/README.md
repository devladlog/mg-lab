# DEVLADLOG Copilot & AI #6 - Copilot in Power Automate

Contoso's facilities team wants a daily **reminder for overdue equipment loans**. Copilot in Power Automate can build the
trigger and actions of a cloud flow from a sentence, edit the flow from a pane in the designer, and explain a failed run.
This episode records what it really does in the lab environment `DEV`, what it needs, and then does the part Copilot cannot
do for you: **review what it built**, with a small Python tool you can run (standard library only, pytest for the tests):

- `copilot_flow_review` has three commands: `prompt` lints a Copilot prompt against Learn's guidance, `flow` reviews a flow
  definition (a JSON file, or the folder from `pac solution unpack`), `expr` checks one workflow expression.

Series plan: [`../../README.md`](../../README.md) (read "Licensing reality in the lab"). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Previous: episode 5, [Copilot in Power Apps](../05-copilot-in-power-apps/).
Next: episode 7, Copilot in Power BI and Fabric (the lab Fabric trial capacity does not support Copilot, per Learn).
Category episodes this builds on: [Cloud flows fundamentals](../../../power-automate/episodes/01-cloud-flows-fundamentals/),
[Approval workflows](../../../power-automate/episodes/02-approval-workflows-business-process/),
[Advanced expressions and functions](../../../power-automate/episodes/03-advanced-expressions-functions/) and
[Power Fx formulas and tips](../../../powerapps/episodes/03-power-fx-formulas-tips/).

| Path | What it is |
|---|---|
| [`src/copilot_flow_review/`](src/copilot_flow_review) | `prompts.py` (prompt linter), `flows.py` (flow reviewer), `expressions.py` (expression checker), `cli.py` |
| [`src/data/wdl-functions.txt`](src/data/wdl-functions.txt) | The 137 function names of the Learn workflow definition language reference |
| [`src/samples/loan-reminders-draft.json`](src/samples/loan-reminders-draft.json) | **Hand-written** flow in the documented shape, with the usual draft habits on purpose. Not Copilot output |
| [`src/samples/loan-reminders-reviewed.json`](src/samples/loan-reminders-reviewed.json) | The same flow after review: Try and Catch scopes, time zone, parameters |
| [`src/samples/prompts.txt`](src/samples/prompts.txt) | Good and bad prompts |
| [`tests/`](tests) | 43 pytest tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (16 scenes, about 890 words) and the recording shot list, starting with `## Lab environment` |

## Rules

| Code | Severity | What |
|---|---|---|
| PL000 / PL005 | error | Empty prompt / "fix my flow" style prompt with nothing to act on |
| PL001 to PL003 | warning | Create prompt without a trigger, without a named connector, or very short |
| PL004, PL006 | warning, info | Edit prompt with about three or more steps in one message; not starting with a verb |
| PL007, PL008 | warning | Asks Copilot to debug a run, or to read your data (Learn: it cannot) |
| FR001 | warning | Literal e-mail address in a recipient field |
| FR002 | warning | Actions with side effects and no action that runs after Failed or TimedOut |
| FR003 | info | A message sent inside a loop |
| FR005 | warning | Recurrence trigger without a time zone |
| FR008, FR009 | warning | Legacy `ApiConnection`; connection instead of connection reference (Learn FAQ: the designer with Copilot cannot edit such flows) |
| FR010 | per finding | Expression findings inside the flow (EX codes below) |
| EX001, EX002 | error, info | Unbalanced brackets or quotes; unknown function name or wrong case (name list from Learn) |
| EX003, EX004 | warning | `D`, `Y` or `S` in a `formatDateTime` pattern (not .NET specifiers); `mm` (minutes) where months were probably meant |

Exit code: 1 when at least one error, 2 for a usage error, 0 otherwise.

## Run and test

```bash
cd series/copilot-ai/episodes/06-copilot-in-power-automate
python3 -m pytest -q                                   # 43 passed
cd src
python3 -m copilot_flow_review flow samples/loan-reminders-draft.json      # 0 errors, 4 warnings, 1 note
python3 -m copilot_flow_review flow samples/loan-reminders-reviewed.json   # 0 errors, 0 warnings, 1 note
python3 -m copilot_flow_review expr "formatDateTime(utcNow(), 'DD-MM')"
python3 -m copilot_flow_review prompt "fix my flow" --mode edit
# real flow: pac solution unpack --zipfile LoanReminders.zip --folder unpacked ; then
python3 -m copilot_flow_review flow unpacked
```

Verified here: `pytest` 43 passed (Python 3.13, Linux). Not verified without the tenant: everything Copilot does, and how
the real flow JSON of a Copilot-built flow reviews (see `demo.md`, "Open points"). `__pycache__` and `.pytest_cache` were deleted after the run.

## What we learned / gotchas

- **The checker cannot evaluate.** It finds shape problems and warns about patterns. What an expression returns is shown
  only by running the flow and opening the Compose output.
- **`formatDateTime` takes .NET custom patterns.** `mm` is minutes, `MM` months, and `D`, `Y`, `S` are not specifiers, so
  they come out as letters. Learn's own sample prompt for the expression assistant is `Format TriggerDate to 'DD-MM' format`.
- **Only the format argument is checked.** Looking at every string for these letters gave false positives on names such as
  `DueDate` and on time zone names.
- **Copilot limits (Learn):** no debugging of runtime errors from the designer, no access to your lists or tables, no fix
  for expired connections, nested logic and complex nested expressions can be wrong; prompt guidance is English-first.
- **Not every flow opens with Copilot.** See FR008 and FR009 and the Learn Copilot FAQ for the full list.
- **Samples are not output of the product.** They are written in the documented shape so the tests are real; the demo
  replaces them with the flow Copilot really builds.

## Learn references

- Copilot in Power Automate overview: https://learn.microsoft.com/power-automate/copilot-overview
- Create flows with Copilot: https://learn.microsoft.com/power-automate/create-cloud-flow-using-copilot
- Prompt tips: https://learn.microsoft.com/power-automate/copilot-cloud-flows-tips
- FAQ: https://learn.microsoft.com/power-automate/faq-copilot-cloud-flows
- Regions: https://learn.microsoft.com/power-automate/regions-overview
- Expression assistant: https://learn.microsoft.com/power-automate/expressions-copilot
- Fix flow failures: https://learn.microsoft.com/power-automate/fix-flow-failures
- Workflow expression functions: https://learn.microsoft.com/azure/logic-apps/workflow-definition-language-functions-reference
