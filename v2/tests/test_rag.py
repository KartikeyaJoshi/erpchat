"""RAG tests (offline — no Pinecone or OpenAI calls)."""

from pathlib import Path

import pytest
from fpdf import FPDF

import app.config as config
from app.rag.knowledge import build_chunks, extract_pdf_pages
from app.rag.service import RagRetrievalError, format_hits_for_prompt, get_schema_context


def _write_pdf(path: Path, text: str) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def test_extract_pdf_pages(tmp_path):
    pdf_path = tmp_path / "schema.pdf"
    _write_pdf(pdf_path, "Table: public.customers\nColumns: credit_limit")
    pages = extract_pdf_pages(pdf_path)
    assert len(pages) == 1
    assert "customers" in pages[0][1].lower()


def test_build_chunks_from_two_pdfs(tmp_path, monkeypatch):
    schema_pdf = tmp_path / "schema.pdf"
    rules_pdf = tmp_path / "business_logic.pdf"
    _write_pdf(schema_pdf, "Table: public.customers\nColumns: credit_limit, company_name")
    _write_pdf(rules_pdf, "Business rules: revenue excludes Draft and Cancelled orders.")

    monkeypatch.setattr(config, "KNOWLEDGE_SCHEMA_PDF", str(schema_pdf))
    monkeypatch.setattr(config, "KNOWLEDGE_RULES_PDF", str(rules_pdf))
    monkeypatch.setattr(config, "KNOWLEDGE_VERSION", "test-1")
    monkeypatch.setattr(config, "PDF_CHUNK_MAX_CHARS", 5000)

    chunks = build_chunks()
    assert len(chunks) >= 2
    schema_chunks = [c for c in chunks if c.doc_type == "schema"]
    rules_chunks = [c for c in chunks if c.doc_type == "rules"]
    assert schema_chunks and rules_chunks
    assert all(c.id.startswith("schema:") for c in schema_chunks)
    assert all(c.id.startswith("rules:") for c in rules_chunks)


def test_get_schema_context_raises_when_embedding_fails(monkeypatch):
    def fail_embed(_text: str):
        raise ValueError("OPENAI_API_KEY is required for RAG embeddings.")

    monkeypatch.setattr("app.rag.service.embed_query_with_usage", lambda text: (fail_embed(text), 0))
    with pytest.raises((RagRetrievalError, ValueError)):
        get_schema_context("top 3 products by revenue")


def test_format_hits_splits_schema_and_rules():
    hits = [
        {"id": "schema:p1", "content": "customers table", "doc_type": "schema", "tables": "customers"},
        {"id": "rules:p1", "content": "revenue metric rules", "doc_type": "rules", "tables": ""},
    ]
    schema, metrics = format_hits_for_prompt(hits)
    assert "customers" in schema
    assert "revenue" in metrics
