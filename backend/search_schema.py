"""Azure AI Search schema shared by ingestion and API workflows."""

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

VECTOR_DIM = 1536


def metadata_fields() -> list:
    """Return the additive Stage 9 fields carried by every SEC filing chunk."""
    return [
        SimpleField(name="year", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="ticker", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="company_name", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="cik", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="form_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="fiscal_year", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="filing_date", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="accession_number", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="sec_url", type=SearchFieldDataType.String),
    ]


def build_search_index(index_name: str) -> SearchIndex:
    """Build the complete schema used when creating a new FilingsIQ index."""
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIM,
            vector_search_profile_name="hnsw-profile",
        ),
        *metadata_fields(),
    ]
    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[
                VectorSearchProfile(
                    name="hnsw-profile",
                    algorithm_configuration_name="hnsw-config",
                )
            ],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="semantic-config",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="content")]
                    ),
                )
            ]
        ),
    )


def ensure_search_index(endpoint: str, key: str, index_name: str) -> None:
    """Create the index or add any missing metadata fields without deleting data."""
    client = SearchIndexClient(endpoint, AzureKeyCredential(key))
    try:
        index = client.get_index(index_name)
    except Exception as exc:
        if getattr(exc, "status_code", None) != 404:
            raise
        client.create_index(build_search_index(index_name))
        return

    existing = {field.name for field in index.fields}
    missing = [field for field in metadata_fields() if field.name not in existing]
    if missing:
        index.fields.extend(missing)
        client.create_or_update_index(index)
