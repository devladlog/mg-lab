# DEVLADLOG Copilot & AI #3 - Copilot Studio: Your First Agent with SharePoint Knowledge

Contoso's Vendor Management Office (VMO) answers the same questions all day: who approves a vendor, when do we pay,
which vendors need a security review. This episode builds the **Contoso Vendor Desk** agent in Copilot Studio, grounded
in a SharePoint site, and adds the tooling that the portal does not give you:

- `kbpack build` turns Markdown policies (with question and answer pairs in the front matter) into real `.docx` files,
  one folder per SharePoint library;
- `kbpack check` tests a folder against the **documented limits and silent failure modes** of SharePoint knowledge
  (file types, 7 MB / 200 MB size limit, classic `.aspx` pages, password-protected files, sensitivity labels,
  documents without a title) and names the Learn page behind every finding;
- `kbpack testset` writes the **evaluation test set** (`Question,Expected response`, the import format of Copilot
  Studio) from the same source and verifies that every expected fact is really in the document;
- `New-VendorKnowledgeSite.ps1` (PnP PowerShell) creates the site, a `Policies` and a `Restricted` library with unique
  permissions, and uploads the files, so the demo can show **security trimming**.

Series plan: [`../../README.md`](../../README.md) (read "Licensing reality in the lab"). Shared lab: [`../../../LAB.md`](../../../LAB.md).
Previous: episode 2, [Microsoft 365 Copilot Chat in a real tenant](../02-microsoft-365-copilot-chat-in-a-real-tenant/)
(same fictional vendors: Fabrikam Cloud, Northwind Print, Adventure Works Travel, Contoso Security Labs).
Next: episode 4, *Copilot Studio: Actions, Agent Flows and Dataverse*, which lets the same agent file a vendor request.
Category episodes this builds on: [SharePoint integration with Power Automate](../../../power-automate/episodes/05-sharepoint-integration/),
[Document management in SharePoint](../../../sharepoint/episodes/04-document-management/),
[Permissions and governance](../../../sharepoint/episodes/05-permissions-governance/) and
[Power Apps ALM and DevOps](../../../powerapps/episodes/09-alm-devops-for-power-platform/).

| Path | What it is |
|---|---|
| [`src/knowledge/*.md`](src/knowledge) | Five fictional policies (four open, one `Restricted`). Front matter: `title`, `library`, `faq` (question, answer, `facts` that must appear in the document) |
| [`src/kbpack/docbuild.py`](src/kbpack/docbuild.py) | Markdown subset to `.docx` (title as Heading 1, tables, fixed timestamps so builds are reproducible) |
| [`src/kbpack/limits.py`](src/kbpack/limits.py) | Every number with the Learn page it comes from |
| [`src/kbpack/readiness.py`](src/kbpack/readiness.py) | The checker: two modes, `site` (SharePoint option) and `files` (Upload files > SharePoint), `--m365-copilot` for the licence-dependent size limit |
| [`src/kbpack/testset.py`](src/kbpack/testset.py) | Test-set CSV builder and validator (100 questions, 1,000 characters), plus a validator for the conversation format (20 conversations, 6 questions) |
| [`src/kbpack/cli.py`](src/kbpack/cli.py) | `python -m kbpack build | check | testset` |
| [`src/scripts/New-VendorKnowledgeSite.ps1`](src/scripts/New-VendorKnowledgeSite.ps1) | Site, libraries, permissions, upload, `-Remove`. Needs the tenant and PnP.PowerShell 3.x |
| [`tests/`](tests) | 33 pytest tests (7 of them run the PowerShell script under `pwsh` with stand-in PnP cmdlets) |
| [`script.yaml`](script.yaml), [`demo.md`](demo.md) | Draft script (15 scenes, about 800 words) and shot list |

## Run and test

```bash
cd series/copilot-ai/episodes/03-copilot-studio-your-first-agent-with-sharepoint-kn
python3 -m pip install -r src/requirements.txt     # python-docx, pypdf, PyYAML, pytest
python3 -m pytest -q                                # 33 passed (needs pwsh for 7 of them)
cd src
python3 -m kbpack build --out ../out/docs
python3 -m kbpack check ../out/docs/Policies        # READY
python3 -m kbpack check ../out/docs/Policies --mode files
python3 -m kbpack testset --docs ../out/docs --out ../out/eval
```

Against the tenant (needs the tenant; see `demo.md`):

```powershell
./src/scripts/New-VendorKnowledgeSite.ps1 -TenantUrl https://<tenant>.sharepoint.com -ClientId <app id> `
    -OwnerUpn <owner UPN> -RestrictedUserUpn <owner UPN> -ReaderUpns <reader UPN> -DocsPath ./out/docs
```

Verified here: pytest 33 passed (Python 3.13, PowerShell 7.6). Not verified without the tenant: the first real run of
the site script (cmdlets and parameters were read from the PnP PowerShell documentation), and everything Copilot Studio
shows. The 'out' folder is generated; do not commit it.

## What we learned / gotchas

All from Microsoft Learn (checked 21 Nov 2026), except where marked.

- **Two SharePoint options in *Add knowledge*.** *Featured > SharePoint* is the full integration: you give a site or
  folder URL, the agent searches that URL and its subfolders, never parents or siblings, and answers only from what the
  signed-in user can read (minimum Read). *Upload file > SharePoint* adds individual files and folders, syncs them (every
  four to six hours), stores them in Dataverse (it consumes Dataverse storage), and does not support document libraries.
  This episode uses the first.
- **Permissions fail silently.** A user without access gets no results, no error: "it appears as if no documents were
  found". The same silence happens when the Entra app registration lacks `Sites.Read.All` / `Files.Read.All` (manual
  authentication), when **Restricted SharePoint Search** is on, and for guest users in SSO-enabled apps.
- **Only the top three search results** are summarised. If Microsoft Search returns nothing, the agent does not answer.
  New files must be indexed first: check by searching a unique word in SharePoint; a site admin can trigger *Re-index site*.
- **Size.** Without a Microsoft 365 Copilot licence in the same tenant as the agent, generative answers use SharePoint
  files **under 7 MB** (and *Tenant graph grounding with semantic search* must be off). With the licence and the setting
  on, up to 200 MB. Larger files are found by search but not processed. `kbpack check` takes `--m365-copilot` for this.
- **Supported content.** Word, PowerPoint and PDF files and modern pages; classic `.aspx` pages and modern pages with
  SPFx components are not used; Excel can be added but the agent cannot run code, so analytical questions suffer; pages
  with an accordion navigation menu or custom CSS are not used.
- **Questions that name a file cannot be answered** ("What does file-name.pdf say?"). `kbpack check` warns when a .docx
  does not start with a Title or Heading 1.
- **Protected files.** Files with an encrypting sensitivity label, DKE or a password can show as *Ready* and still give
  "no response". Detection here: an encrypted `.docx/.pptx/.xlsx` is an OLE container instead of a ZIP (magic bytes),
  an encrypted PDF is read with pypdf, and labels are read from `docProps/custom.xml` (`MSIP_Label_*_Name`; this
  last detail is how Office stamps labels, it is not stated on Learn, so it is reported as a warning only).
- **Keep general knowledge and web search off** when answers must come only from your documents (Learn, generative
  answers and the SharePoint filter section). Then, with no result, the agent answers "no response".
- **Trial licence: build and test, not publish.** Test chat usage is not billed. Published rates: classic answer 1
  Copilot Credit, generative answer 2, tenant graph grounding 10, agent action 5; Microsoft 365 Copilot licensed users
  are not charged for these answers. Pay-as-you-go price per credit: see series episode 1 (US$0.01, with source).
- **Product names move.** Learn now describes three harnesses (standard, Microsoft Copilot, Customer Conversation) and
  says to turn off *New experience* to get the standard agent used here. "Actions" are now **tools**; "Power Virtual
  Agents" is the old name of Copilot Studio. Check what your create-agent page shows before you record.
- **Evaluation CSV.** Single response import: header `Question`, `Expected response`, up to 100 questions, 1,000
  characters each; expected responses are optional for import but needed by Compare meaning, Text similarity and Exact
  match; results are kept 89 days (export to keep them); the run uses the signed-in user's connections. The newer
  experience and the CLI describe a different layout (`conversationNumber,question,response`, 20 conversations of up
  to 6 questions): `kbpack.testset.validate_conversation_csv` checks that one too.
- **PnP:** interactive sign-in needs your own Entra app (`-ClientId`) since 9 September 2024; role names such as `Read`
  are localised, so the script is written for an English-language site.

## References

Microsoft Learn
- [Add SharePoint as a knowledge source](https://learn.microsoft.com/microsoft-copilot-studio/knowledge-add-sharepoint)
- [Quotas and limits (SharePoint web app limits)](https://learn.microsoft.com/microsoft-copilot-studio/requirements-quotas)
- [Add unstructured data as a knowledge source (Upload files > SharePoint)](https://learn.microsoft.com/microsoft-copilot-studio/knowledge-add-unstructured-data)
- [SharePoint knowledge sources don't return results in Copilot Studio](https://learn.microsoft.com/troubleshoot/power-platform/copilot-studio/knowledge/sharepoint-no-response)
- [Knowledge in Copilot Studio (tenant graph grounding, web search, official sources)](https://learn.microsoft.com/microsoft-copilot-studio/knowledge-copilot-studio)
- [Use generative answers in a topic (general knowledge, content moderation)](https://learn.microsoft.com/microsoft-copilot-studio/nlu-boost-node)
- [Quickstart: create and deploy an agent with the standard harness](https://learn.microsoft.com/microsoft-copilot-studio/fundamentals-get-started)
- [Create a single response test set](https://learn.microsoft.com/microsoft-copilot-studio/analytics-agent-evaluation-create)
- [Evaluate an agent (preview): test methods and CSV layout](https://learn.microsoft.com/microsoft-copilot-studio/agents-experience/analytics-agent-evaluation-intro)
- [Billing rates and management (Copilot Credits)](https://learn.microsoft.com/microsoft-copilot-studio/requirements-messages-management)
- [Licensing for agents powered by the standard harness](https://learn.microsoft.com/microsoft-copilot-studio/billing-licensing)
- [FAQ for Copilot Studio billing and licensing](https://learn.microsoft.com/microsoft-copilot-studio/faq-billing-licensing)
- [Harnesses in Copilot Studio](https://learn.microsoft.com/microsoft-copilot-studio/harnesses-overview)

Other official documentation
- [PnP PowerShell: Connect-PnPOnline](https://pnp.github.io/powershell/cmdlets/Connect-PnPOnline.html),
  [New-PnPSite](https://pnp.github.io/powershell/cmdlets/New-PnPSite.html),
  [New-PnPList](https://pnp.github.io/powershell/cmdlets/New-PnPList.html),
  [Set-PnPList](https://pnp.github.io/powershell/cmdlets/Set-PnPList.html),
  [Set-PnPListPermission](https://pnp.github.io/powershell/cmdlets/Set-PnPListPermission.html),
  [Add-PnPFile](https://pnp.github.io/powershell/cmdlets/Add-PnPFile.html),
  [Remove-PnPTenantSite](https://pnp.github.io/powershell/cmdlets/Remove-PnPTenantSite.html)

No devladlog.com blog guide: this series is built from vendor documentation only.
