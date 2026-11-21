"""The real azure-search-documents SDK against a local stub of the search REST API (no cloud needed)."""
import pytest

pytest.importorskip("azure.search.documents")

from azure.core.credentials import AzureKeyCredential  # noqa: E402
from azure.search.documents import SearchClient  # noqa: E402
from azure.search.documents.indexes import SearchIndexClient  # noqa: E402

from hrrag.chunking import chunk_folder  # noqa: E402
from hrrag.index_schema import build_index  # noqa: E402
from hrrag.ingest import batches, to_documents, upload  # noqa: E402
from hrrag.retrieve import search  # noqa: E402

API_VERSION = "api-version=2026-10-01"  # GA version targeted by azure-search-documents 12.1.0


def client(stub):
    # The stub is plain HTTP, and the SDK refuses bearer tokens over HTTP, so tests use a fake key.
    # The real code paths use DefaultAzureCredential (Entra ID + RBAC).
    return SearchClient(stub.url, "hr-handbook", AzureKeyCredential("fake"))


def test_create_index_sends_vectorizer_and_semantic_config(stub_server):
    stub_server.responses.append((201, {}, lambda body: body))
    SearchIndexClient(stub_server.url, AzureKeyCredential("fake")).create_or_update_index(
        build_index("https://contoso-aoai.openai.azure.com", "embed-small"))
    req = stub_server.requests[0]
    assert req["method"] == "PUT" and req["path"] == f"/indexes('hr-handbook')?{API_VERSION}"
    assert req["body"]["vectorSearch"]["vectorizers"][0]["kind"] == "azureOpenAI"
    assert req["body"]["semantic"]["defaultConfiguration"] == "hr-semantic"


def test_upload_sends_merge_or_upload_with_vectors(stub_server, handbook):
    chunks = chunk_folder(handbook)[:3]
    docs = to_documents(chunks, [[0.1] * 4 for _ in chunks])
    stub_server.responses.append((200, {}, {"value": [
        {"key": d["id"], "status": True, "errorMessage": None, "statusCode": 201} for d in docs]}))
    assert upload(client(stub_server), docs) == 3
    req = stub_server.requests[0]
    assert req["path"] == f"/indexes('hr-handbook')/docs/search.index?{API_VERSION}"
    first = req["body"]["value"][0]
    assert first["@search.action"] == "mergeOrUpload" and first["content_vector"] == [0.1] * 4


def test_partial_failure_is_not_silent(stub_server):
    stub_server.responses.append((207, {}, {"value": [
        {"key": "a", "status": True, "errorMessage": None, "statusCode": 201},
        {"key": "b", "status": False, "errorMessage": "Invalid field value", "statusCode": 400}]}))
    with pytest.raises(RuntimeError, match="b: 400 Invalid field value"):
        upload(client(stub_server), [{"id": "a"}, {"id": "b"}])


def test_batches_respect_the_1000_document_limit():
    assert [len(b) for b in batches(list(range(2500)), 1000)] == [1000, 1000, 500]
    with pytest.raises(ValueError):
        list(batches([1], 1001))


RESULT = {"@search.score": 0.0325, "@search.rerankerScore": 2.87, "id": "leave-carry-over-0", "source": "leave",
          "section_key": "leave#carry-over", "section": "Carry-over", "content": "Leave policy > Carry-over ..."}


def test_hybrid_semantic_query_shape_and_reranker_score(stub_server):
    stub_server.responses.append((200, {}, {"value": [RESULT]}))
    hits = search(client(stub_server), "Can I keep unused holiday?", "hybrid_semantic")
    body = stub_server.requests[0]["body"]
    assert body["search"] == "Can I keep unused holiday?"
    assert body["vectorQueries"] == [{"kind": "text", "text": "Can I keep unused holiday?", "k": 50, "fields": "content_vector"}]
    assert body["queryType"] == "semantic" and body["semanticConfiguration"] == "hr-semantic"
    assert body["top"] == 5
    assert hits[0].section_key == "leave#carry-over" and hits[0].reranker_score == pytest.approx(2.87)


@pytest.mark.parametrize("mode,has_text,has_vector", [("keyword", True, False), ("vector", False, True), ("hybrid", True, True)])
def test_each_mode_sends_only_what_it_needs(stub_server, mode, has_text, has_vector):
    stub_server.responses.append((200, {}, {"value": []}))
    search(client(stub_server), "mileage rate", mode)
    body = stub_server.requests[0]["body"]
    assert ("search" in body) is has_text
    assert ("vectorQueries" in body) is has_vector
    assert "queryType" not in body
