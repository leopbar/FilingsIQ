"""
add_year_field.py — One-time migration: adds a filterable 'year' field to
filingsiq-pipeline-index and patches all 640 existing chunks with their year.

Run once from backend/:
    python add_year_field.py

What it does:
  1. Updates the index schema to add 'year' (filterable string).
  2. Merges year into every existing chunk document using their known IDs.
     No re-embedding needed — only the year field is added.
"""

import os

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
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
from dotenv import load_dotenv

load_dotenv()

PIPELINE_INDEX = os.environ.get("AZURE_SEARCH_PIPELINE_INDEX_NAME", "filingsiq-pipeline-index")
VECTOR_DIM     = 1536
UPLOAD_BATCH   = 50

# Chunk counts per fiscal year — from the S5.5 pipeline run.
FY_CHUNKS = {2021: 136, 2022: 132, 2023: 123, 2024: 124, 2025: 125}

endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
key      = os.environ["AZURE_SEARCH_KEY"]


def update_index_schema() -> None:
    idx_client = SearchIndexClient(endpoint, AzureKeyCredential(key))

    fields = [
        SimpleField(name="id",   type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=VECTOR_DIM,
            vector_search_profile_name="hnsw-profile",
        ),
        SimpleField(name="year", type=SearchFieldDataType.String, filterable=True),
    ]

    index = SearchIndex(
        name=PIPELINE_INDEX,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
            profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")],
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

    idx_client.create_or_update_index(index)
    print(f"Schema updated — '{PIPELINE_INDEX}' now has a filterable 'year' field.")


def patch_year_field() -> None:
    search_client = SearchClient(
        endpoint=endpoint,
        index_name=PIPELINE_INDEX,
        credential=AzureKeyCredential(key),
    )

    total = 0
    for fy, count in FY_CHUNKS.items():
        docs = [{"id": f"fy{fy}-chunk-{i}", "year": f"FY{fy}"} for i in range(count)]

        for i in range(0, len(docs), UPLOAD_BATCH):
            results = search_client.merge_documents(documents=docs[i : i + UPLOAD_BATCH])
            failed  = [r for r in results if not r.succeeded]
            if failed:
                print(f"  FY{fy}: {len(failed)} failures — {[r.key for r in failed[:5]]}")

        total += count
        print(f"  FY{fy}: {count} chunks patched.")

    print(f"\nDone. {total} total chunks now have a 'year' field.")


if __name__ == "__main__":
    print("Step 1 — Updating index schema ...")
    update_index_schema()

    print("\nStep 2 — Patching 'year' field into existing chunks ...")
    patch_year_field()
