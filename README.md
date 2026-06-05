# ERPChat — ERP Analyst Prototype

**Ask business questions in plain English. Get answers from your ERP data.**

ERPChat is an interactive demo that shows how an AI assistant can work on top of enterprise resource planning (ERP) data. You can browse the database structure, ask questions in everyday language, and receive answers — without writing SQL yourself.

---

## The problem it solves

ERP systems hold valuable data across sales, inventory, finance, and HR — but getting answers usually means knowing table names, writing queries, or waiting on a report. ERPChat explores a simpler path: **you ask a question, the system figures out the rest.**

This is a **prototype**, not a finished product. It is meant to demonstrate the idea, gather feedback, and show how natural language can connect to structured business data.

---

## What can you do?

### Landing page (`/`)
A marketing-style intro with an overview of features, how the demo works, and a **Try Now** button to open the chat.

### Schema browser (`/schema`)
Explore the live database structure:
- Tables grouped and searchable
- Column names, types, primary keys, and foreign keys
- Relationship map between tables
- Sample rows from each table

Schema data is cached in the browser until you refresh or clear site data.

### Chat (`/chat`)
Ask business questions in plain language, for example:
- *What is total revenue in 2026?*
- *What is stock at Mumbai Warehouse?*
- *What is the salary for Diya Sharma?*

When the AI finds multiple matching records, it asks you to pick the right one instead of guessing.

> **AI can make mistakes** — always verify important figures against the source data.

---

## How it works (behind the scenes)

When you send a question, the backend runs a multi-step pipeline:

```
Your question
    ↓
Planner — understands intent and picks the right tables
    ↓
SQL generator — writes a database query
    ↓
SQL validator — checks syntax, schema, and safety rules
    ↓
Database — runs the query against live ERP data
    ↓
Insight — returns a clear answer in plain language
```

**RAG (retrieval-augmented generation)** pulls relevant context from schema and business-rule documents so the AI stays aligned with your data model.

**Disambiguation** kicks in when a name or term could match more than one record — you choose, and the pipeline continues with your selection.

---

## Tech stack

### Frontend (`frontend/`)

| Technology | Role |
|------------|------|
| **React 19** | User interface |
| **Vite** | Development and build tooling |
| **React Router** | Navigation between pages |
| **Framer Motion** | Animations on landing and chat |
| **Plain CSS** | Styling with light/dark theme support |

### Backend (`v2/`)

| Technology | Role |
|------------|------|
| **FastAPI** | REST API server |
| **LangGraph** | Orchestrates the AI pipeline as a graph of steps |
| **Groq (LLM)** | Powers planning, SQL generation, and answers |
| **PostgreSQL** | ERP data storage |
| **SQLGlot** | Validates SQL before it hits the database |
| **Pinecone + OpenAI** | Vector search over knowledge documents (RAG) |

---

## Project structure

```
ERP Analyst Agent/
├── frontend/              # React web app
│   └── src/
│       ├── pages/         # Landing, Chat, Schema
│       ├── components/    # UI building blocks
│       ├── context/       # Shared state (chat, schema, theme)
│       ├── api/           # Calls to the backend
│       └── hooks/         # Reusable logic
├── v2/                    # Python API
│   └── app/
│       ├── main.py        # API routes
│       ├── graph.py       # LangGraph pipeline
│       ├── nodes.py       # Pipeline steps
│       ├── schema/        # Live schema explorer
│       ├── validator/     # SQL safety checks
│       └── rag/           # Knowledge retrieval
├── DOCS/                  # Product docs
└── README.md

# Kept locally only (not in git):
# v1/  — earlier prototype version
```

---

## Run locally

### Backend

```powershell
cd v2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Add your API keys to .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

In development, the frontend automatically forwards `/api` and `/health` requests to the backend on port `8001`.

---

## API overview

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Check if the API is running |
| `POST` | `/api/v1/analyze` | Send a business question |
| `GET` | `/api/v1/schema` | Fetch live database schema |
| `GET` | `/api/v1/schema/tables/{name}/preview` | Sample rows for one table |
| `GET` | `/api/v1/metrics` | Pipeline usage metrics |

---

## Who is this for?

- **Product & business teams** — see what natural-language ERP access could look like
- **Developers** — study the LangGraph pipeline, SQL validation, and RAG setup
- **Stakeholders** — try the demo without installing a full ERP reporting tool

---

## License

Prototype / demonstration project. Use and adapt as needed for your team.
