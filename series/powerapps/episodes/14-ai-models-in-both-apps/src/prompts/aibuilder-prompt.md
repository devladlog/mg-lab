# AI Builder prompt: Inspection triage (needs Copilot Credits)

Create it in make.powerapps.com > AI hub > Prompts > Build your own prompt.
Model: leave the default. Output: JSON. This prompt consumes Copilot Credits every time it runs, in the tenant's credit capacity.

## Inputs
| Name | Type | Sample |
|---|---|---|
| Notes | Text | Fire door in the east stairwell is wedged open with a fire extinguisher. |
| Photo | Image or document | (a real photo from the lab app; never a stock image) |

## Prompt text
Paste the whole of `system.md`, then add these two lines:

Notes: [Notes]
Photo: [Photo]

## Output
Select JSON and use the sample from `src/eval/sample-output.json`.
