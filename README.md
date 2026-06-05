# ERPChat — ERP Analyst Prototype

**Ask business questions in plain English. Get answers from your ERP data.**

ERPChat is an interactive prototype that lets you explore a live database schema and chat with an AI analyst about revenue, inventory, payroll, customers, and more — without writing SQL.

---

## What does it do?

| Feature | In simple terms |
|--------|------------------|
| **Landing page** | Introduces the project and links to the demo |
| **Schema browser** | Shows live tables, columns, relationships, and sample rows |
| **Chat** | Ask questions like *"What is total revenue in 2026?"* and get answers |
| **Smart follow-ups** | When several records match, the AI asks you to pick the right one |

> **Note:** This is a prototype for demonstration — not a full production product. AI can make mistakes; verify important numbers against source data.

---

## Tech stack

### Frontend (`frontend/`)
| Technology | Purpose |
|------------|---------|
| **React 19** | UI framework |
| **Vite** | Fast dev server & build tool |
| **React Router** | Pages: `/`, `/chat`, `/schema` |
| **Framer Motion** | Smooth animations on landing & chat |
| **Plain CSS** | Light/dark theme with CSS variables |

### Backend (`v2/`)
| Technology | Purpose |
|------------|---------|
| **FastAPI** | REST API |
| **LangGraph** | Multi-step AI pipeline (plan → SQL → answer) |
| **Groq (LLM)** | Natural language understanding & SQL generation |
| **PostgreSQL via Supabase** | Live ERP data storage |
| **SQLGlot** | SQL validation before execution |
| **Pinecone + OpenAI** | RAG over schema & business rules PDFs |

---

## Project structure

```
ERP Analyst Agent/
├── frontend/          # React app (Vercel)
│   └── src/
│       ├── pages/     # Landing, Chat, Schema
│       ├── components/
│       └── context/   # Chat, Schema, Theme state
├── v2/                # FastAPI API (Render)
│   └── app/
│       ├── main.py    # API routes
│       ├── graph.py   # LangGraph pipeline
│       └── schema/    # Live DB explorer
├── render.yaml        # Render deployment blueprint
└── README.md

# Not uploaded to GitHub (see .gitignore):
# v1/  — old prototype, kept locally only
```

---

## Run locally

### 1. Backend

```powershell
cd v2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Fill in API keys in .env (see v2/.env.example)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**

The dev server proxies `/api` and `/health` to the backend automatically.

---

## Deploy: Backend on Render

### Step 1 — Push code to GitHub

```powershell
cd "D:\DEV\ERP Analyst Agent"
git init
git add .
git commit -m "Initial commit: ERPChat prototype"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/erp-analyst-agent.git
git push -u origin main
```

### Step 2 — Create a Render Web Service

1. Go to [render.com](https://render.com) → **New** → **Web Service**
2. Connect your GitHub repo
3. Configure:

| Setting | Value |
|---------|-------|
| **Name** | `erp-analyst-api` |
| **Root Directory** | `v2` |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Health Check Path** | `/health` |

> **Tip:** You can also use the included `render.yaml` blueprint: **New** → **Blueprint** → point at your repo.

### Step 3 — Add environment variables on Render

Copy from `v2/.env.example`. **Required minimum:**

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | LLM for planning & SQL |
| `SUPABASE_URL` | Database URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Database access |
| `OPENAI_API_KEY` | Embeddings for RAG |
| `PINECONE_API_KEY` | Vector search |
| `PINECONE_INDEX_NAME` | Your Pinecone index |
| `FRONTEND_URL` | Your Vercel URL (add after Step 4) |

### Step 4 — Note your API URL

After deploy, Render gives you a URL like:

`https://erp-analyst-api.onrender.com`

Test it: `https://erp-analyst-api.onrender.com/health` → should return `{"status":"ok",...}`

---

## Deploy: Frontend on Vercel

### Step 1 — Import project

1. Go to [vercel.com](https://vercel.com) → **Add New** → **Project**
2. Import the same GitHub repo
3. Configure:

| Setting | Value |
|---------|-------|
| **Framework Preset** | Vite |
| **Root Directory** | `frontend` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |

### Step 2 — Environment variable

| Variable | Value |
|----------|-------|
| `VITE_API_BASE_URL` | `https://erp-analyst-api.onrender.com` (your Render URL, **no trailing slash**) |

### Step 3 — Deploy

Click **Deploy**. Vercel will build and host your app at e.g. `https://erpchat.vercel.app`.

`frontend/vercel.json` is included so React Router paths (`/chat`, `/schema`) work correctly.

### Step 4 — Connect frontend ↔ backend

Go back to **Render** → your API service → **Environment** → set:

```
FRONTEND_URL=https://your-app.vercel.app
```

Save and redeploy the API so CORS allows your Vercel domain.

---

## Deployment checklist

- [ ] GitHub repo created and code pushed
- [ ] Render API deployed, `/health` returns OK
- [ ] All backend env vars set on Render
- [ ] Vercel frontend deployed with `VITE_API_BASE_URL`
- [ ] `FRONTEND_URL` set on Render to Vercel URL
- [ ] Chat page shows **Connected** status pill
- [ ] Schema page loads tables

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/analyze` | Send a business question |
| `GET` | `/api/v1/schema` | Live database schema |
| `GET` | `/api/v1/schema/tables/{name}/preview` | Sample rows for a table |
| `GET` | `/api/v1/metrics` | Pipeline metrics |

---

## Free tier notes

- **Render free** services spin down after inactivity — first request may take 30–60 seconds to wake up.
- **Vercel** hobby tier is fine for this static React build.
- Never commit `.env` files — use platform environment variable UIs instead.

---

## License

Prototype / demonstration project. Use and modify as needed for your team.
