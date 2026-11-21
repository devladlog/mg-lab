"""The search index for the Contoso HR handbook, built with the azure-search-documents models.

One document per chunk. Text fields for BM25 and the semantic ranker, one vector field for HNSW, a vectorizer so
the service turns query text into a vector itself (integrated vectorization at query time), and a semantic
configuration. Facts checked on Microsoft Learn:
- The vectorizer and the indexing-time embeddings must use the same embedding model; changing the vectorizer does
  not re-embed documents ("Configure a vectorizer").
- With neither apiKey nor authIdentity, the Azure OpenAI vectorizer calls the model with the search service's
  system-assigned managed identity, which needs Cognitive Services OpenAI User on the Azure OpenAI resource.
- text-embedding-3-small: up to 1536 dimensions; the vector field's dimensions must match.
"""
from __future__ import annotations

from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

INDEX_NAME = "hr-handbook"
VECTOR_FIELD = "content_vector"
VECTOR_PROFILE = "hr-vector-profile"
VECTORIZER = "hr-aoai-vectorizer"
SEMANTIC_CONFIG = "hr-semantic"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MODEL_MAX_DIMENSIONS = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072, "text-embedding-ada-002": 1536}


def build_index(
    aoai_endpoint: str,
    embedding_deployment: str,
    *,
    name: str = INDEX_NAME,
    model_name: str = EMBEDDING_MODEL,
    dimensions: int = EMBEDDING_DIMENSIONS,
) -> SearchIndex:
    if dimensions > MODEL_MAX_DIMENSIONS[model_name]:
        raise ValueError(f"{model_name} produces at most {MODEL_MAX_DIMENSIONS[model_name]} dimensions")
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="section_key", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="section", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name=VECTOR_FIELD,
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            hidden=True,  # never returned: we only need it for similarity
            vector_search_dimensions=dimensions,
            vector_search_profile_name=VECTOR_PROFILE,
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hr-hnsw", parameters=HnswParameters(metric="cosine"))],
        profiles=[VectorSearchProfile(name=VECTOR_PROFILE, algorithm_configuration_name="hr-hnsw", vectorizer_name=VECTORIZER)],
        vectorizers=[
            AzureOpenAIVectorizer(
                vectorizer_name=VECTORIZER,
                parameters=AzureOpenAIVectorizerParameters(
                    resource_url=aoai_endpoint.rstrip("/"),
                    deployment_name=embedding_deployment,
                    model_name=model_name,
                    # no api_key, no auth_identity -> the search service's system-assigned managed identity
                ),
            )
        ],
    )
    semantic = SemanticSearch(
        default_configuration_name=SEMANTIC_CONFIG,
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="section"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="title")],
                ),
            )
        ],
    )
    return SearchIndex(name=name, fields=fields, vector_search=vector_search, semantic_search=semantic)
