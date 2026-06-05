#!/usr/bin/env python3
"""
Index the knowledge PDF into Pinecone.

Steps:
  1. Put PDFs at app/knowledge/schema.pdf and app/knowledge/business_logic.pdf
  2. Set OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME in .env
  3. Create a Pinecone index (1536 dimensions, cosine)
  4. Run: python scripts/index_knowledge_base.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.rag.knowledge import build_chunks
from app.rag.pinecone_store import upsert_chunks
from app.rag.service import embed_texts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print chunks only.")
    args = parser.parse_args()

    chunks = build_chunks()
    print(f"Chunks: {len(chunks)}")

    if args.dry_run:
        for c in chunks:
            print(f"  {c.id} ({c.doc_type})")
        return 0

    vectors = embed_texts([c.text for c in chunks])
    count = upsert_chunks(chunks, vectors)
    print(f"Upserted {count} vectors. Restart the API to use RAG.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
