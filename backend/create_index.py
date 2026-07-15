"""
One-time script: creates the Azure AI Search index for FilingsIQ.

Fields
------
id        : unique key for each chunk
content   : the raw text (keyword / BM25 searchable)
embedding : 1 536-float vector (HNSW, for vector search)
metadata  : company, filing identity, fiscal year, and SEC provenance fields

After creation the index also has a semantic configuration that tells
the re-ranker to use the `content` field as the primary content field.

Run once:
    python create_index.py
"""

import os

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from dotenv import load_dotenv

from search_schema import build_search_index

load_dotenv()

ENDPOINT  = os.environ["AZURE_SEARCH_ENDPOINT"]
KEY       = os.environ["AZURE_SEARCH_KEY"]
INDEX     = os.environ["AZURE_SEARCH_INDEX_NAME"]

def main():
    client = SearchIndexClient(ENDPOINT, AzureKeyCredential(KEY))
    result = client.create_or_update_index(build_search_index(INDEX))
    print(f"Index '{result.name}' created/updated successfully.")

if __name__ == "__main__":
    main()
