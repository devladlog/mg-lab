# DEVLADLOG Copilot & AI #17 - Extending Microsoft 365 Copilot: Declarative Agents and API Plugins

Episodes 3 and 4 built the **Contoso Vendor Desk** in Copilot Studio. This episode builds a Vendor Desk the pro-code way:
a **declarative agent** for Microsoft 365 Copilot that calls a small REST API through an **API plugin** (Learn now says
*actions*: the agent holds the instructions, the plugin manifest and the OpenAPI description describe the tools).
It runs on Copilot's own orchestrator and model, so there is nothing to host except your API.

Everything that can be checked offline is checked offline, with tests: the manifests against Microsoft's published JSON
schemas, the OpenAPI description against Learn's rules, the package zip, and the real API code against the OpenAPI
response schemas. What only a tenant can do (upload the app, run it in Copilot Chat) is in [`demo.md`](demo.md).

Series plan: [`../../README.md`](../../README.md). Shared lab: [`../../../LAB.md`](../../../LAB.md). Builds on:
[episode 2, Copilot Chat in a real tenant](../02-microsoft-365-copilot-chat-in-a-real-tenant/),
[episode 3, first agent with SharePoint knowledge](../03-copilot-studio-your-first-agent-with-sharepoint-kn/) (same
vendor policy), [episode 4, actions, agent flows and Dataverse](../04-copilot-studio-actions-agent-flows-and-dataverse/)
(the low-code way to the same goal) and
[episode 9, Copilot in SharePoint](../09-copilot-in-sharepoint-and-sharepoint-agents/). Licensing background:
[Microsoft 365 Copilot for Microsoft 365](../../../microsoft-365/episodes/08-microsoft-365-copilot-for-microsoft-365/).

## Names that changed

| Old | Current (Learn, checked 2026-11-21) |
|---|---|
| Teams Toolkit | **Microsoft 365 Agents Toolkit** (older route). **Work IQ Dev Tools** (`wiqd`) is now the recommended pro-code tool for supported declarative-agent scenarios. This episode builds the package by hand so every file is visible |
| Plugin (for a declarative agent) | **Action**. A *Microsoft 365 Copilot plugin* is now an installable package; an *API plugin* or *MCP plugin* gives actions to an agent |
| Graph connectors | **Microsoft 365 Copilot connectors** |

## What is in this folder

| Path | What it is |
|---|---|
| [`src/agent/appPackage/manifest.json`](src/agent/appPackage/manifest.json) | App manifest 1.30 with one entry in `copilotAgents.declarativeAgents` |
| [`src/agent/appPackage/declarativeAgent.json`](src/agent/appPackage/declarativeAgent.json) | Declarative agent manifest v1.9: instructions, conversation starters, `discourage_model_knowledge`, one action |
| [`src/agent/appPackage/vendor-renewals-plugin.json`](src/agent/appPackage/vendor-renewals-plugin.json) | API plugin manifest v2.4: three functions, confirmation card, response template, API key auth by vault reference |
| [`src/agent/appPackage/openapi.yaml`](src/agent/appPackage/openapi.yaml) | OpenAPI 3.0.3: `listRenewals`, `getVendor`, `createDecisionReminder` |
| [`src/agent/appPackage/adaptiveCards/renewal.json`](src/agent/appPackage/adaptiveCards/renewal.json) | Adaptive Card template for a renewal |
| [`src/vendor_api/`](src/vendor_api) | The API: stdlib WSGI, bearer key, rules from episode 3 (decide 90 days before renewal, escalate at 60) |
| [`src/dakit/`](src/dakit) | `dakit`: validate, lint-openapi, licence, contract, package |
| [`src/schemas/`](src/schemas) | The three official JSON schemas, vendored so the tests run offline |
| [`src/samples/declarativeAgent.with-knowledge.json`](src/samples/declarativeAgent.with-knowledge.json) | A variant with code interpreter, SharePoint and email, to show what needs a licence |
| [`tests/`](tests) | 78 pytest tests |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (about 800 words) and the shot list with `## Lab environment` |

The data is fictional (Contoso, Fabrikam Cloud, Northwind Print, Jordan Demo ...). The app id in `manifest.json` is
the placeholder `${{APP_ID}}`; `dakit package` substitutes a real GUID, the tunnel URL and the API key registration id.

## Run and test

```bash
cd series/copilot-ai/episodes/17-extending-microsoft-365-copilot-declarative-agents
python3 -m pip install -r src/requirements.txt
python3 -m pytest -q                                   # 78 passed

cd src
python3 -m dakit validate agent/appPackage             # 0 error(s), 0 warning(s)
python3 -m dakit lint-openapi agent/appPackage/openapi.yaml
python3 -m dakit contract agent/appPackage/openapi.yaml
python3 -m dakit licence agent/appPackage/declarativeAgent.json --max all    # exit 1 if it needs more than Copilot Chat
python3 -m dakit licence samples/declarativeAgent.with-knowledge.json        # Required: licensed
VENDOR_API_KEY=<any-string> python3 -m vendor_api --today 2026-11-21 --port 8080
python3 -m dakit package agent/appPackage --out ../vendor-desk.zip --app-id <new-guid> \
    --api-url https://<tunnel>.devtunnels.ms --auth-id <api-key-registration-id> --version 1.0.0
```

`dakit validate` uses the official schemas with a Draft 7 validator on purpose: the schemas declare draft-04 but use
`const`, and a draft-04 validator silently ignores it (a wrong `manifestVersion` would pass). It also reports
unrecognised properties, because Learn says they make a declarative agent manifest invalid even though the schema
does not forbid them.

## What the tests cover

- **Schemas and cross-file rules:** all three manifests, every function name has an `operationId`, `run_for_functions`
  names exist, referenced files exist, instruction and conversation-starter limits, confirmation and `security_info`
  present for the write operation, no unresolved placeholder in a built package.
- **OpenAPI lint (Learn's document guidance):** valid 3.0.x, `https` server, descriptions, no nested objects in
  request bodies, no `oneOf`/`allOf`/`anyOf`, no cycles, no cookie keys, no OAuth flows beyond what the plugin supports.
- **API rules:** decide/escalate dates, status values, reminder date window, note length, auth (401 without the key,
  constant-time compare), error bodies.
- **Contract test:** the real API is called in process and each response is validated against the response schema in
  `openapi.yaml`, so the description Copilot reads cannot drift from the code.
- **Licence tiers:** capability table from Learn (all / pay-as-you-go / licensed); a capability not in the table is
  reported, not guessed.
- **Package:** deterministic zip, `manifest.json` first, 192x192 and 32x32 icons, substituted values, validated again.

## Gotchas (all from Learn)

1. **One agent per app** (`copilotAgents.declarativeAgents` takes one entry in manifest 1.30).
2. **Upload custom apps** must be allowed by an admin in a Teams setup policy; it can take up to 24 hours to apply.
3. **Dev tunnel access is anonymous** for local debugging, and that is separate from your API's auth: the API still
   checks its own key.
4. **API key auth** is registered in the Teams Developer Portal; the manifest only holds the registration id
   (`reference_id`), never the key.
5. **OpenAPI limits:** flat request objects, no polymorphism, https, `operationId` on every operation. Descriptions are
   what the model reads: write them as instructions.
6. **Licence:** custom actions and instructions work in Copilot Chat without usage-based billing. SharePoint, connectors,
   embedded files and Dataverse need pay-as-you-go or a Copilot licence; email, people, Teams messages and meetings
   need a licence.
7. **Confirmation:** a write function without `confirmation` runs without asking; the lint warns.

## Verified here and not

Verified in the build container (Linux, Python 3.13): `python3 -m pytest -q` gave **78 passed**; the CLI commands above
ran clean; the API ran for real and answered `listRenewals` with the Fabrikam Cloud row.
**Not verified without a tenant:** that Teams accepts the hand-built zip, that Copilot Chat picks the functions from the
descriptions and renders the card, dev tunnel and API key registration behaviour, the Copilot Chat licence tier claim
for this exact agent (taken from the Learn table, not tested), and the manifest `confirmation` wording on screen.
Nothing was uploaded, signed in or created in any cloud.

## References

- [Prerequisites and licensing for plugins](https://learn.microsoft.com/microsoft-365/copilot/extensibility/prerequisites)
- [Declarative agent manifest 1.9](https://learn.microsoft.com/microsoft-365/copilot/extensibility/declarative-agent-manifest-1.9)
- [API plugin manifest 2.4](https://learn.microsoft.com/microsoft-365/copilot/extensibility/plugin-manifest-2.4)
- [OpenAPI document guidance](https://learn.microsoft.com/microsoft-365/copilot/extensibility/openapi-document-guidance)
- [Known issues](https://learn.microsoft.com/microsoft-365/copilot/extensibility/known-issues)
- [API key authentication](https://learn.microsoft.com/microsoft-365/copilot/extensibility/plugin-authentication-api-key)
- [Package an API plugin](https://learn.microsoft.com/microsoft-365/copilot/extensibility/package-plugin)
- [App package](https://learn.microsoft.com/microsoft-365/copilot/extensibility/app-package)
- [Debug agents](https://learn.microsoft.com/microsoft-365/copilot/extensibility/debugging-agents)
- [Choose plugin development tools](https://learn.microsoft.com/microsoft-365/copilot/extensibility/choose-plugin-development-tools)
- [Teams custom app policies and settings](https://learn.microsoft.com/microsoftteams/teams-custom-app-policies-and-settings)
- [Dev tunnels CLI commands](https://learn.microsoft.com/azure/developer/dev-tunnels/cli-commands)
- [Compare declarative and custom engine agents](https://learn.microsoft.com/microsoft-365/copilot/extensibility/agents-overview)

Some of these Learn paths were resolved by search and may have moved to the newer `/plugins/` location (the FAQ and
agent overview currently serve from there). Re-check the links when you record.
