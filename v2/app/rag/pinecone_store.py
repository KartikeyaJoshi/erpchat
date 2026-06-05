"""
Pinecone vector database: upload chunks and search by similarity.

Requires a Pinecone index with dimension matching EMBEDDING_DIMENSIONS (default 1536).
Create the index in the Pinecone console or run: python scripts/index_knowledge_base.py
"""

from __future__ import annotations

from functools import lru_cache

from pinecone import Pinecone

from app import config
from app.rag.knowledge import Chunk


def _chunk_metadata(chunk: Chunk) -> dict:
    """Pinecone metadata must use simple types; we store full text for retrieval."""
    return {
        "content": chunk.text,
        "doc_type": chunk.doc_type,
        "schema_version": chunk.schema_version,
        "tables": ",".join(chunk.tables),
    }


@lru_cache(maxsize=1)
def _pinecone_index():
    if not config.PINECONE_API_KEY:
        raise ValueError("PINECONE_API_KEY is not set.")
    client = Pinecone(api_key=config.PINECONE_API_KEY)
    return client.Index(config.PINECONE_INDEX_NAME)


def upsert_chunks(chunks: list[Chunk], vectors: list[list[float]]) -> int:
    """Write or update all chunk vectors in Pinecone."""
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must have the same length.")

    records = [
        {
            "id": chunk.id,
            "values": vector,
            "metadata": _chunk_metadata(chunk),
        }
        for chunk, vector in zip(chunks, vectors)
    ]
    if not records:
        return 0

    namespace = config.PINECONE_NAMESPACE
    _pinecone_index().upsert(vectors=records, namespace=namespace)
    return len(records)


def search(
    query_vector: list[float],
    *,
    top_k: int,
    schema_version: str,
) -> list[dict]:
    """
    Find the most similar chunks.

    Returns dicts with keys: id, content, doc_type, score.
    """
    response = _pinecone_index().query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
        namespace=config.PINECONE_NAMESPACE,
        filter={"schema_version": {"$eq": schema_version}},
    )

    raw_matches = getattr(response, "matches", None)
    if raw_matches is None and isinstance(response, dict):
        raw_matches = response.get("matches")
    raw_matches = raw_matches or []

    hits: list[dict] = []
    for match in raw_matches:
        if isinstance(match, dict):
            match_id = match.get("id", "")
            score = float(match.get("score") or 0.0)
            meta = match.get("metadata") or {}
        else:
            match_id = getattr(match, "id", "")
            score = float(getattr(match, "score", 0.0) or 0.0)
            meta = getattr(match, "metadata", None) or {}

        hits.append(
            {
                "id": match_id,
                "content": meta.get("content", ""),
                "doc_type": meta.get("doc_type", ""),
                "score": score,
                "tables": meta.get("tables", ""),
            }
        )
    return hits
