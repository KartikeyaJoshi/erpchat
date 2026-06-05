# ERP Analyst Agent v2 — Phase 1

Phase 1 stabilization scaffold: **deterministic defaults**, **SQL/schema validation**, **error taxonomy**, and **baseline observability**.

## Layout

```
v2/
  app/
    main.py              # FastAPI + trace middleware + classified responses
    graph.py             # LangGraph with sql_validator gate
    nodes.py             # Pipeline nodes
    config.py            # Model, prompt versions, guardrails
    contracts/           # Pydantic request/response/error models
    schema/              # Governed ERP schema (JSON) + prompt formatter
    validator/           # Pre-execution SQL checks (SQLGlot)
    observability/       # Trace ID, structured logs, in-memory metrics
  tests/
```

## Pipeline (vs v1)

**Single-target (default):**

```
planner → sql_generator → sql_validator → database_executor → python_analyzer → insight_synthesizer
```

**Multi-step (Option B)** — when the planner detects multiple distinct questions:

```
planner → [sql_generator → sql_validator → database_executor] × N targets → python_analyzer → insight
```

Each target gets its own SQL against the relevant tables only. Results are merged in `target_results` and the insight is sectioned per target (deterministic, no LLM digit guessing).

**Partial completion:** If target 2 fails validation but target 1 succeeded, the pipeline still runs insight with `status: partial` and sectioned results (failed targets show error text).

**SQL templates:** Known targets (`high_credit_outstanding`, `fast_movers_low_stock`) use deterministic SQL to avoid hallucinated tables like `top_products`.

## Run locally

```powershell
cd "d:\ERP Analyst Agent\v2"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Fill GROQ_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (same as v1)

uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

## API

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/analyze` | Run analysis (`query`, `deterministic`, `include_sql`) |
| `GET /api/v1/metrics` | Baseline metrics snapshot |
| `GET /health` | Health check |

Response includes `trace_id`, `validation`, `error` (taxonomy), `prompt_versions`, `retry_count`.

Pass `X-Trace-Id` header to correlate logs.

## Tests

```powershell
cd v2
pytest tests/ -v
```

Validator tests run offline (no API keys required).

## RAG (PDF → Pinecone)

**Chunking source:** two PDFs:

| File | Env var | Default path |
|------|---------|----------------|
| Schema | `KNOWLEDGE_SCHEMA_PDF` | `app/knowledge/schema.pdf` |
| Business logic | `KNOWLEDGE_RULES_PDF` | `app/knowledge/business_logic.pdf` |

**SQL validation:** still uses `app/schema/erp_schema.json` (not the PDFs).

Every request embeds the question, searches Pinecone, and injects matching chunks. RAG must be configured and indexed; there is no static-schema fallback.

### Setup

1. Copy your PDFs to the paths above (or set env vars).
   ```powershell
   python scripts/generate_knowledge_pdf.py   # optional starter PDFs from JSON/md
   ```
2. Create a Pinecone index: **1536 dimensions**, metric **cosine**.
3. Set `.env`: `OPENAI_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, both PDF paths.
4. Index:
   ```powershell
   python scripts/index_knowledge_base.py --dry-run
   python scripts/index_knowledge_base.py
   ```
5. Bump `KNOWLEDGE_VERSION` when you replace either PDF, then re-index.

### RAG code

| File | Role |
|------|------|
| `app/rag/knowledge.py` | Read PDF, split into chunks |
| `app/rag/pinecone_store.py` | Upload and search vectors |
| `app/rag/service.py` | Embeddings + `get_schema_context()` |

## Phase 1 scope

Included in this scaffold:

- Structured planner output (Pydantic)
- SQL validator (syntax, schema allowlist, read-only policy, complexity)
- Classified API errors (no bare 500 for graph failures)
- Trace ID + structured JSON logs + `/api/v1/metrics`

Deferred to Phase 2/3 (per PRD):

- Multi-step query orchestration
- Advanced SQL templates (cohorts, windows, etc.)
- Evidence-linked insights with confidence scoring
