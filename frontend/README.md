# ERP Analyst Chat (React)

Chatbot UI for the ERP Business Data Analyst Agent API.

## Prerequisites

- Node.js 18+
- Backend running (from repo root):

```bash
uvicorn --app-dir v2 app.main:app --reload --host 0.0.0.0 --port 8001
```

## Setup

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

The dev server proxies `/api` and `/health` to `http://127.0.0.1:8001` by default.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `` (empty) | API origin. Leave empty to use Vite proxy in dev. |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8001` | Proxy target (vite.config.js only) |

Copy `.env.example` to `.env.local` to override.

## Features

- Natural-language questions to `/api/v1/analyze`
- Clarification option buttons when multiple records match
- Automatic follow-up with `resolved_filters` (hidden from Swagger, used by UI)
- Connection status indicator
- Starter question chips

## Production build

```bash
npm run build
npm run preview
```

Set `VITE_API_BASE_URL` to your deployed API URL when building for production.
