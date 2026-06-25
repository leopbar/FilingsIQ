"""
One-time script: creates the Azure AI Search index for FilingsIQ.

Fields
------
id        : unique key for each chunk
content   : the raw text (keyword / BM25 searchable)
embedding : 1 536-float vector (HNSW, for vector search)

After creation the index also has a semantic configuration that tells
the re-ranker to use the `content` field as the primary content field.

Run once:
    python create_index.py
"""

import os
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
)

load_dotenv()

ENDPOINT  = os.environ["AZURE_SEARCH_ENDPOINT"]
KEY       = os.environ["AZURE_SEARCH_KEY"]
INDEX     = os.environ["AZURE_SEARCH_INDEX_NAME"]

VECTOR_DIM = 1536   # text-embedding-3-small output size

def main():
    client = SearchIndexClient(ENDPOINT, AzureKeyCredential(KEY))

    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
        ),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIM,
            vector_search_profile_name="hnsw-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")],
    )

    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="semantic-config",
                prioritized_fields=SemanticPrioritizedFields(
                    content_fields=[SemanticField(field_name="content")]
                ),
            )
        ]
    )

    index = SearchIndex(
        name=INDEX,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )

    result = client.create_or_update_index(index)
    print(f"Index '{result.name}' created/updated successfully.")

if __name__ == "__main__":
    main()
