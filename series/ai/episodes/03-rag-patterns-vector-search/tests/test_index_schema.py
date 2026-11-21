import pytest

from hrrag.index_schema import EMBEDDING_DIMENSIONS, SEMANTIC_CONFIG, VECTOR_FIELD, build_index


@pytest.fixture
def rest():
    """The index exactly as the SDK sends it to the REST API."""
    return build_index("https://contoso-aoai.openai.azure.com/", "embed-small").as_dict()


def test_vector_field_matches_the_embedding_model(rest):
    field = next(f for f in rest["fields"] if f["name"] == VECTOR_FIELD)
    assert field["type"] == "Collection(Edm.Single)"
    assert field["dimensions"] == EMBEDDING_DIMENSIONS == 1536
    assert field["searchable"] is True and field["retrievable"] is False


def test_profile_links_hnsw_and_the_vectorizer(rest):
    vs = rest["vectorSearch"]
    field = next(f for f in rest["fields"] if f["name"] == VECTOR_FIELD)
    profile = next(p for p in vs["profiles"] if p["name"] == field["vectorSearchProfile"])
    assert profile["algorithm"] in {a["name"] for a in vs["algorithms"]}
    assert profile["vectorizer"] in {v["name"] for v in vs["vectorizers"]}
    assert vs["algorithms"][0]["kind"] == "hnsw" and vs["algorithms"][0]["hnswParameters"]["metric"] == "cosine"


def test_vectorizer_is_keyless_and_names_the_model(rest):
    v = rest["vectorSearch"]["vectorizers"][0]
    assert v["kind"] == "azureOpenAI"
    p = v["azureOpenAIParameters"]
    assert p == {"resourceUri": "https://contoso-aoai.openai.azure.com", "deploymentId": "embed-small",
                 "modelName": "text-embedding-3-small"}  # no apiKey, no authIdentity -> system managed identity


def test_semantic_configuration_and_key(rest):
    assert rest["semantic"]["defaultConfiguration"] == SEMANTIC_CONFIG
    cfg = rest["semantic"]["configurations"][0]["prioritizedFields"]
    assert cfg["titleField"]["fieldName"] == "section"
    assert [f["fieldName"] for f in cfg["prioritizedContentFields"]] == ["content"]
    assert [f["name"] for f in rest["fields"] if f.get("key")] == ["id"]


def test_dimensions_above_the_model_maximum_are_rejected():
    with pytest.raises(ValueError):
        build_index("https://x.openai.azure.com", "embed", dimensions=3072)  # 3-small tops out at 1536
