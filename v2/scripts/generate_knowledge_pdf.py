#!/usr/bin/env python3
"""
Bootstrap starter PDFs from erp_schema.json + business_rules.md.

Outputs:
  app/knowledge/schema.pdf
  app/knowledge/business_logic.pdf

Replace these with your real documents, then run: python scripts/index_knowledge_base.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fpdf import FPDF

SCHEMA_FILE = ROOT / "app" / "schema" / "erp_schema.json"
RULES_FILE = ROOT / "app" / "knowledge" / "business_rules.md"
SCHEMA_PDF = ROOT / "app" / "knowledge" / "schema.pdf"
RULES_PDF = ROOT / "app" / "knowledge" / "business_logic.pdf"


def _pdf_safe(text: str) -> str:
    return (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


def _write_pdf(path: Path, lines: list[str]) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    width = pdf.epw
    for line in lines:
        safe = _pdf_safe(line)
        if not safe.strip():
            pdf.ln(4)
            continue
        pdf.multi_cell(width, 5, safe)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def main() -> int:
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    rules = RULES_FILE.read_text(encoding="utf-8") if RULES_FILE.is_file() else ""

    schema_lines = ["ERP Database Schema", ""]
    for table, meta in schema.get("tables", {}).items():
        schema_lines.append(f"Table: public.{table}")
        schema_lines.append(f"Primary key: {meta.get('primary_key', '')}")
        schema_lines.append(f"Columns: {', '.join(meta.get('columns', []))}")
        for col, values in (meta.get("enums") or {}).items():
            schema_lines.append(f"  {col} values: {', '.join(values)}")
        for col, ref in (meta.get("foreign_keys") or {}).items():
            schema_lines.append(f"  FK {col} -> {ref}")
        schema_lines.append("")

    schema_lines.extend(["Join paths", ""])
    for path in schema.get("join_paths") or []:
        if len(path) >= 3:
            schema_lines.append(f"- {path[0]} JOIN {path[1]} ON {path[2]}")
        else:
            schema_lines.append(f"- {' -> '.join(path)}")

    rules_lines = ["ERP Business Logic", ""]
    if rules:
        rules_lines.append(rules)
    else:
        rules_lines.append("Add business rules in app/knowledge/business_rules.md and re-run this script.")

    for name, desc in (schema.get("metric_definitions") or {}).items():
        rules_lines.append(f"- {name}: {desc}")

    _write_pdf(SCHEMA_PDF, schema_lines)
    _write_pdf(RULES_PDF, rules_lines)
    print(f"Wrote {SCHEMA_PDF}")
    print(f"Wrote {RULES_PDF}")
    print("Next: python scripts/index_knowledge_base.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
