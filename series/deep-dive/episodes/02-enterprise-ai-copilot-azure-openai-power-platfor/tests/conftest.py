import base64
import json
import sys
from pathlib import Path

import pytest
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from stubs import Stub  # noqa: E402

from copilot.retrieval import Retriever  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EMPLOYEES = "00000000-0000-0000-0000-000000000001"
MANAGERS = "00000000-0000-0000-0000-000000000002"
ALEX = "00000000-0000-0000-0000-00000000a1e7"


def principal(groups=(EMPLOYEES,), oid=ALEX, name="alex.demo@contoso.com", extra=(), mapped=False) -> str:
    """Build an X-MS-CLIENT-PRINCIPAL header value like App Service does."""
    g_typ = "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups" if mapped else "groups"
    o_typ = "http://schemas.microsoft.com/identity/claims/objectidentifier" if mapped else "oid"
    claims = [{"typ": o_typ, "val": oid}, {"typ": "name", "val": name}]
    claims += [{"typ": g_typ, "val": g} for g in groups] + list(extra)
    doc = {"auth_typ": "aad", "name_typ": "name", "role_typ": "roles", "claims": claims}
    return base64.b64encode(json.dumps(doc).encode()).decode()


def policy_docs():
    """The four fictional policies as already-indexed chunks (what the indexer would push)."""
    sys.path.insert(0, str(ROOT / "indexer"))
    from chunking import chunk_markdown
    acl = {"leave-policy": [EMPLOYEES], "travel-policy": [EMPLOYEES], "it-faq": [EMPLOYEES],
           "salary-bands": [MANAGERS]}
    docs = []
    for p in sorted((ROOT / "data" / "policies").glob("*.md")):
        for i, c in enumerate(chunk_markdown(p.read_text(encoding="utf-8"), p.stem)):
            docs.append({"id": f"{p.stem}_{i}", "title": c.title, "url": f"https://contoso.sharepoint.com/sites/hr-lab/{p.name}",
                         "chunk": c.text, "group_ids": acl[p.stem]})
    return docs


@pytest.fixture
def stub():
    with Stub(docs=policy_docs()) as s:
        yield s


@pytest.fixture
def retriever(stub):
    client = SearchClient(stub.endpoint, "hr-policies", AzureKeyCredential("stub"))
    return Retriever(client)


@pytest.fixture
def llm(stub):
    # api_key is a callable, exactly like the keyless token provider in production
    return OpenAI(base_url=f"{stub.endpoint}/openai/v1/", api_key=lambda: "stub-token", max_retries=0)
