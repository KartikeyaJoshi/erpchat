"""
RAG service: embed questions, search Pinecone, build LLM prompt context.

Flow:
  1. User question -> embedding (OpenAI)
  2. Pinecone similarity search -> top chunks
  3. Format chunks -> schema_context + metric_definitions for prompts

Requires a indexed PDF in Pinecone. Errors are raised (no static-schema fallback).
"""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from app import config
from app.observability.logging import log_event
from app.rag import pinecone_store

_RULE_TYPES = frozenset({"rules", "metrics"})
_openai_client: OpenAI | None = None


class RagRetrievalError(RuntimeError):
    """Raised when Pinecone returns no usable knowledge for a query."""


@dataclass(frozen=True)
class SchemaContext:
    """Text blocks injected into planner and SQL generator prompts."""

    schema_context: str
    metric_definitions: str
    embedding_tokens: int = 0


def _openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for RAG embeddings.")
        _openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Turn text into vectors using the configured OpenAI embedding model."""
    if not texts:
        return []
    kwargs: dict = {"model": config.EMBEDDING_MODEL, "input": texts}
    if "text-embedding-3" in config.EMBEDDING_MODEL:
        kwargs["dimensions"] = config.EMBEDDING_DIMENSIONS
    response = _openai().embeddings.create(**kwargs)
    ordered = sorted(response.data, key=lambda row: row.index)
    return [row.embedding for row in ordered]


def _embedding_usage_tokens(response: object) -> int:
    usage = getattr(response, "usage", None)
    total = getattr(usage, "total_tokens", 0) if usage is not None else 0
    try:
        return int(total or 0)
    except (TypeError, ValueError):
        return 0


def embed_texts_with_usage(texts: list[str]) -> tuple[list[list[float]], int]:
    if not texts:
        return [], 0
    kwargs: dict = {"model": config.EMBEDDING_MODEL, "input": texts}
    if "text-embedding-3" in config.EMBEDDING_MODEL:
        kwargs["dimensions"] = config.EMBEDDING_DIMENSIONS
    response = _openai().embeddings.create(**kwargs)
    ordered = sorted(response.data, key=lambda row: row.index)
    vectors = [row.embedding for row in ordered]
    return vectors, _embedding_usage_tokens(response)


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def embed_query_with_usage(text: str) -> tuple[list[float], int]:
    vectors, tokens = embed_texts_with_usage([text])
    return vectors[0], tokens


def _search_text(query: str, intent: str | None, tables: list[str] | None) -> str:
    parts = [query.strip()]
    if intent:
        parts.append(intent.strip())
    if tables:
        parts.append("Tables: " + ", ".join(tables))
    return "\n".join(parts)


def _prefer_table(hits: list[dict], tables: list[str] | None) -> list[dict]:
    """When SQL targets specific tables, prefer chunks that mention them."""
    if not tables:
        return hits
    preferred = [
        h
        for h in hits
        if not h.get("tables") or any(t in h["tables"] for t in tables)
    ]
    return preferred if preferred else hits


def format_hits_for_prompt(hits: list[dict]) -> tuple[str, str]:
    """Split search results into schema block and metrics/rules block."""
    if not hits:
        return "", ""

    schema_lines = ["RELEVANT SCHEMA (from knowledge base):"]
    metric_lines = ["RELEVANT BUSINESS RULES (from knowledge base):"]

    for hit in hits:
        block = f"\n--- {hit['id']} ---\n{hit['content'].strip()}"
        if hit.get("doc_type") in _RULE_TYPES:
            metric_lines.append(block)
        else:
            schema_lines.append(block)

    schema = "\n".join(schema_lines) if len(schema_lines) > 1 else ""
    metrics = "\n".join(metric_lines) if len(metric_lines) > 1 else ""
    return schema, metrics


def get_schema_context(
    query: str,
    *,
    intent: str | None = None,
    tables: list[str] | None = None,
) -> SchemaContext:
    """Load prompt context from Pinecone. Raises RagRetrievalError if nothing matches."""
    version = config.KNOWLEDGE_VERSION
    vector, embedding_tokens = embed_query_with_usage(_search_text(query, intent, tables))
    hits = pinecone_store.search(
        vector,
        top_k=config.RAG_TOP_K,
        schema_version=version,
    )
    hits = _prefer_table(hits, tables)

    if not hits:
        log_event("rag_no_hits", "rag")
        raise RagRetrievalError(
            "No knowledge chunks matched this query. "
            "Check Pinecone index, KNOWLEDGE_VERSION, and run: "
            "python scripts/index_knowledge_base.py"
        )

    schema_ctx, metric_ctx = format_hits_for_prompt(hits)
    if not schema_ctx.strip():
        raise RagRetrievalError(
            "Matched chunks did not contain schema text. Re-index the knowledge PDF."
        )

    log_event("rag_ok", "rag", extra={"hits": [h["id"] for h in hits[:5]]})
    return SchemaContext(
        schema_context=schema_ctx,
        metric_definitions=metric_ctx,
        embedding_tokens=embedding_tokens,
    )
