"""Chunking, document building, Graph source (httpx2 MockTransport) and the ingest job into the Search stub."""
import base64
import json
import re

import httpx2 as httpx
import pytest
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from conftest import EMPLOYEES, MANAGERS, ROOT
from openai import OpenAI

import cli
from chunking import chunk_markdown
from graph_source import GRAPH, DriveFile, GraphSource
from push import build_documents, doc_key, index_definition, make_embedder, upload

LEAVE = (ROOT / "data" / "policies" / "leave-policy.md").read_text(encoding="utf-8")
F = DriveFile("b!drive-0001", "01ITEM0001", "leave-policy.md", "https://contoso.sharepoint.com/sites/hr-lab/Policies/leave-policy.md",
              "2026-11-01T10:00:00Z", "leave-policy.md")


def fake_embed(texts):
    return [[0.1, 0.2, 0.3] for _ in texts]


def test_chunks_keep_title_and_heading_path():
    chunks = chunk_markdown(LEAVE, "leave-policy")
    assert [c.heading for c in chunks] == [
        "Contoso annual leave policy (fictional) > Entitlement",
        "Contoso annual leave policy (fictional) > Carry-over",
        "Contoso annual leave policy (fictional) > Requesting leave"]
    assert all(c.title == "Contoso annual leave policy (fictional)" for c in chunks)
    assert chunks[1].text.startswith("Contoso annual leave policy (fictional) > Carry-over\nUp to 5 unused days")


def test_long_sections_are_split_with_overlap_and_nothing_is_lost():
    body = " ".join(f"Sentence number {i} about leave." for i in range(200))
    chunks = chunk_markdown(f"# T\n## S\n{body}", "t", max_chars=500, overlap=80)
    assert len(chunks) > 5 and all(len(c.text) <= 500 + len("T > S\n") for c in chunks)
    for i in (0, 57, 199):
        assert any(f"Sentence number {i} " in c.text for c in chunks)


def test_documents_carry_groups_vectors_and_valid_keys():
    docs = build_documents(F, LEAVE.encode(), [EMPLOYEES], fake_embed)
    assert len(docs) == 3
    for d in docs:
        assert d["group_ids"] == [EMPLOYEES]
        assert re.fullmatch(r"[A-Za-z0-9_\-=]+", d["id"]), d["id"]       # allowed key characters only
        assert d["content_vector"] == [0.1, 0.2, 0.3] and d["@search.action"] == "mergeOrUpload"
    assert base64.urlsafe_b64decode(docs[0]["id"].rsplit("_", 1)[0]) == b"b!drive-0001|01ITEM0001"


def test_a_document_without_groups_is_never_indexed():
    with pytest.raises(ValueError, match="no groups"):
        build_documents(F, LEAVE.encode(), [], fake_embed)


def test_group_names_instead_of_object_ids_are_refused():
    with pytest.raises(ValueError, match="not an Entra group object id"):
        build_documents(F, LEAVE.encode(), ["HR Managers"], fake_embed)


def test_office_files_are_skipped_not_indexed_as_garbage():
    docx = DriveFile("d", "i", "handbook.docx", "u", "2026-11-01T10:00:00Z", "handbook.docx")
    assert build_documents(docx, b"PK\x03\x04...", [EMPLOYEES], fake_embed) == []


def test_keys_are_stable_per_file_and_chunk():
    assert doc_key(F, 0) == doc_key(F, 0) != doc_key(F, 1)


# ---- Graph ---------------------------------------------------------------------------------------------

def graph_transport(seen):
    pages = {
        "/v1.0/sites/contoso.sharepoint.com:/sites/hr-lab": {"id": "contoso.sharepoint.com,site-guid,web-guid"},
        "/v1.0/sites/contoso.sharepoint.com,site-guid,web-guid/drives": {"value": [
            {"id": "drv-pol", "name": "Policies"}, {"id": "drv-mgr", "name": "Managers"}]},
    }
    files = {
        "drv-pol": [("i1", "leave-policy.md"), ("fold", None), ("i3", "handbook.docx")],
        "drv-pol/fold": [("i2", "travel-policy.md")],
        "drv-mgr": [("i4", "salary-bands.md")],
    }
    texts = {"i1": "leave-policy.md", "i2": "travel-policy.md", "i4": "salary-bands.md", "i3": None}

    def handler(req: httpx.Request):
        seen.append(req)
        path = req.url.path
        if req.url.host == "download.example":
            name = texts[req.url.path.strip("/")]
            return httpx.Response(200, content=(ROOT / "data" / "policies" / name).read_bytes() if name else b"PK\x03\x04")
        if path in pages:
            return httpx.Response(200, json=pages[path])
        m = re.fullmatch(r"/v1.0/drives/([^/]+)/items/([^/]+)/(children|content)", path)
        if m and m.group(3) == "content":
            return httpx.Response(302, headers={"Location": f"https://download.example/{m.group(2)}"})
        if m:
            key = m.group(1) if m.group(2) == "root" else f"{m.group(1)}/{m.group(2)}"
            items = files[key]
            if key == "drv-pol" and "page" not in str(req.url):        # first page -> nextLink
                value, nxt = items[:2], f"{GRAPH}/drives/drv-pol/items/root/children?page=2&$select=id"
            elif key == "drv-pol":
                value, nxt = items[2:], None
            else:
                value, nxt = items, None
            body = {"value": [{"id": i, "name": n or "Archive", "webUrl": f"https://contoso.sharepoint.com/x/{n}",
                               "lastModifiedDateTime": "2026-11-01T10:00:00Z", **({"file": {}} if n else {"folder": {}})}
                              for i, n in value]}
            if nxt:
                body["@odata.nextLink"] = nxt
            return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": {"code": "itemNotFound", "message": path}})

    return httpx.MockTransport(handler)


@pytest.fixture
def graph():
    seen = []
    return GraphSource(lambda: "graph-token", httpx.Client(transport=graph_transport(seen))), seen


def test_graph_lists_files_through_folders_and_pages(graph):
    src, _ = graph
    site = src.site_id("contoso.sharepoint.com:/sites/hr-lab")
    files = list(src.iter_files(src.drive_id(site, "Policies")))
    assert [f.path for f in files] == ["leave-policy.md", "Archive/travel-policy.md", "handbook.docx"]


def test_unknown_library_lists_the_ones_that_exist(graph):
    src, _ = graph
    with pytest.raises(LookupError, match="Found: Policies, Managers"):
        src.drive_id("contoso.sharepoint.com,site-guid,web-guid", "Finance")


def test_download_follows_the_redirect_without_sending_our_token(graph):
    src, seen = graph
    data = src.download(DriveFile("drv-pol", "i1", "leave-policy.md", "u", "t", "leave-policy.md"))
    assert data.startswith(b"# Contoso annual leave policy")
    graph_call, download_call = seen[-2], seen[-1]
    assert graph_call.headers["Authorization"] == "Bearer graph-token"
    assert download_call.url.host == "download.example" and "Authorization" not in download_call.headers


def test_ingest_end_to_end_into_the_search_stub(graph, stub):
    src, _ = graph
    stub.docs.clear()
    config = json.loads((ROOT / "indexer" / "libraries.json").read_text(encoding="utf-8"))
    search = SearchClient(stub.endpoint, "hr-policies", AzureKeyCredential("stub"))
    embed = make_embedder(OpenAI(base_url=f"{stub.endpoint}/openai/v1/", api_key="x", max_retries=0), "embed")
    lines = []
    counts = cli.ingest(config, src, embed, search, log=lines.append)
    assert counts == {"files": 3, "skipped": 1, "chunks": len(stub.docs)}
    by_title = {d["title"]: d["group_ids"] for d in stub.docs}
    assert by_title["Contoso salary bands 2027 (fictional, managers only)"] == [MANAGERS]
    assert by_title["Contoso annual leave policy (fictional)"] == [EMPLOYEES]
    assert any(line.startswith("skip  Policies/handbook.docx") for line in lines)
    assert all(len(d["content_vector"]) == 3 for d in stub.docs)


def test_upload_raises_when_search_rejects_documents():
    class R:
        def __init__(self, key, ok):
            self.key, self.succeeded = key, ok

    class Client:
        def merge_or_upload_documents(self, documents):
            return [R(d["id"], d["id"] != "bad") for d in documents]

    assert upload(Client(), [{"id": "a"}, {"id": "b"}]) == 2
    with pytest.raises(RuntimeError, match="first: bad"):
        upload(Client(), [{"id": "a"}, {"id": "bad"}])


def test_create_index_puts_the_definition_with_a_bearer_token(monkeypatch):
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(201, json={})

    class Cred:
        def get_token(self, scope):
            assert scope == "https://search.azure.com/.default"
            return type("T", (), {"token": "search-token"})()

    monkeypatch.setenv("SEARCH_ENDPOINT", "https://srch-contoso.search.windows.net")
    monkeypatch.setenv("SEARCH_INDEX", "hr-policies")
    monkeypatch.setenv("OPENAI_ENDPOINT", "https://aoai-contoso.openai.azure.com/")
    assert cli.create_index(Cred(), httpx.Client(transport=httpx.MockTransport(handler))) == 201
    (req,) = seen
    assert req.method == "PUT" and req.url.path == "/indexes/hr-policies"
    assert req.url.params["api-version"] == "2026-10-01"
    body = json.loads(req.content)
    assert body["vectorSearch"]["vectorizers"][0]["azureOpenAIParameters"]["resourceUri"] == "https://aoai-contoso.openai.azure.com"


def test_index_definition_security_and_vector_settings():
    idx = index_definition("https://aoai-contoso.openai.azure.com")
    f = {x["name"]: x for x in idx["fields"]}
    assert f["group_ids"] == {"name": "group_ids", "type": "Collection(Edm.String)", "filterable": True, "retrievable": False}
    assert f["content_vector"]["dimensions"] == 1536 and f["content_vector"]["retrievable"] is False
    vz = idx["vectorSearch"]["vectorizers"][0]
    assert vz["kind"] == "azureOpenAI" and vz["azureOpenAIParameters"]["modelName"] == "text-embedding-3-small"
    assert "apiKey" not in vz["azureOpenAIParameters"]          # Search calls Azure OpenAI with its own identity
    prof = idx["vectorSearch"]["profiles"][0]
    assert f["content_vector"]["vectorSearchProfile"] == prof["name"] and prof["vectorizer"] == vz["name"]
    from copilot.retrieval import SELECT
    assert set(SELECT) <= {n for n, x in f.items() if x.get("retrievable")}
