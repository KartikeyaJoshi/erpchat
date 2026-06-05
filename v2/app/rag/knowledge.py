"""
Build RAG chunks from two PDFs: schema + business logic.

SQL validation still uses app/schema/erp_schema.json — only RAG reads the PDFs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app import config
from app.schema.loader import allowed_tables

_KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"
_DEFAULT_SCHEMA_PDF = _KNOWLEDGE_DIR / "schema.pdf"
_DEFAULT_RULES_PDF = _KNOWLEDGE_DIR / "business_logic.pdf"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Chunk:
    """One piece of knowledge to embed and store in Pinecone."""

    id: str
    text: str
    doc_type: str  # schema | rules
    tables: tuple[str, ...] = ()
    schema_version: str = "1.0.0"


def resolve_pdf_path(env_value: str, default: Path) -> Path:
    """Turn .env path into an absolute Path under the v2 project root."""
    raw = env_value.strip()
    path = Path(raw) if raw else default
    if path.is_absolute():
        return path
    return _PROJECT_ROOT / path


def schema_pdf_path() -> Path:
    return resolve_pdf_path(config.KNOWLEDGE_SCHEMA_PDF, _DEFAULT_SCHEMA_PDF)


def rules_pdf_path() -> Path:
    return resolve_pdf_path(config.KNOWLEDGE_RULES_PDF, _DEFAULT_RULES_PDF)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    """Read each non-empty page from a PDF."""
    if not path.is_file():
        raise FileNotFoundError(
            f"Knowledge PDF not found: {path}\n"
            "Set KNOWLEDGE_SCHEMA_PDF and KNOWLEDGE_RULES_PDF in .env, or place files at:\n"
            f"  {_DEFAULT_SCHEMA_PDF}\n"
            f"  {_DEFAULT_RULES_PDF}"
        )

    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for number, page in enumerate(reader.pages, start=1):
        text = _normalize(page.extract_text() or "")
        if text:
            pages.append((number, text))
    if not pages:
        raise ValueError(f"No text extracted from PDF: {path}")
    return pages


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Split long page text into embed-friendly pieces."""
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start + max_chars // 2:
                end = newline
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        start = max(end, start + 1)
    return parts


def _tables_in_text(text: str) -> tuple[str, ...]:
    lower = text.lower()
    return tuple(sorted(t for t in allowed_tables() if t in lower))


def _chunks_from_pdf(
    pdf_path: Path,
    *,
    source: str,
    doc_type: str,
    version: str,
    max_chars: int,
) -> list[Chunk]:
    """Chunk one PDF; ids look like schema:p1 or rules:p2:part1."""
    chunks: list[Chunk] = []
    for page_num, page_text in extract_pdf_pages(pdf_path):
        for part_idx, piece in enumerate(_split_long_text(page_text, max_chars)):
            suffix = "" if part_idx == 0 else f":part{part_idx}"
            chunks.append(
                Chunk(
                    id=f"{source}:p{page_num}{suffix}",
                    text=piece,
                    doc_type=doc_type,
                    tables=_tables_in_text(piece),
                    schema_version=version,
                )
            )
    return chunks


def build_chunks() -> list[Chunk]:
    """Create chunks from schema PDF (doc_type=schema) and business logic PDF (doc_type=rules)."""
    version = config.KNOWLEDGE_VERSION
    max_chars = config.PDF_CHUNK_MAX_CHARS

    schema_chunks = _chunks_from_pdf(
        schema_pdf_path(),
        source="schema",
        doc_type="schema",
        version=version,
        max_chars=max_chars,
    )
    rules_chunks = _chunks_from_pdf(
        rules_pdf_path(),
        source="rules",
        doc_type="rules",
        version=version,
        max_chars=max_chars,
    )
    return schema_chunks + rules_chunks
