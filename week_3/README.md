# Week 3: Resume Helper Full-Stack Chatbot

## Project Overview

This project is a Week 3 full-stack system integration application for the K Youth Python for Real World Systems course. It combines a FastAPI frontend, a FastAPI backend, Docker Compose orchestration, an Ollama local LLM service, and earlier Week 1 and Week 2 data-processing work.

The application helps a user interact with a resume assistant. It supports normal chat, uploaded resume PDF text extraction, resume summarization, skill-gap analysis, and a small database dashboard for Week 1 job data.

The main Week 3 services are:

- `week_3/frontend`: FastAPI + Jinja frontend that serves the landing page, chat page, dashboard page, and frontend proxy API.
- `week_3/backend`: FastAPI backend that receives chat requests and routes them through local Ollama or the copied Week 2 skill-gap workflow.
- `week_3/docker-compose.yml`: Orchestrates frontend, backend, and Ollama on one Docker network.
- `week_3/backend/src/week_2`: Self-contained copy of the Week 2 runtime needed by the backend container.

The final application uses the frontend as the browser-facing entry point. The frontend proxies chat requests to the backend so the browser does not need to call the backend container directly.

## Setup Instructions

### Prerequisites

Install these before running the project:

- Docker Desktop
- `uv`
- Python `3.14.*`
- A local Ollama-compatible model, defaulting to `deepseek-r1:1.5b`

Docker Desktop must be running before Docker or Docker Compose commands will work.

### Docker Compose Setup

From the repository root:

```powershell
cd week_3
docker compose up --build
```

Open the frontend at:

```text
http://127.0.0.1:8000/
```

Useful routes:

- `http://127.0.0.1:8000/`: landing page
- `http://127.0.0.1:8000/chat`: resume helper chatbot
- `http://127.0.0.1:8000/dashboard`: Week 1 jobs dashboard
- `http://127.0.0.1:8001/`: backend health check

The Compose stack contains:

- `frontend`, published on host port `8000`
- `backend`, published on host port `8001` for course testing and debugging
- `ollama`, available inside the Docker network at `http://ollama:11434`

Each service can also start by itself. The frontend still serves `/`, `/chat`, and
`/dashboard` if the backend, Ollama, or Week 1 database is missing; unavailable
features return clear fallback messages instead of stopping the container.

If the Ollama container does not already have the model, pull it after the stack starts:

```powershell
docker compose exec ollama ollama pull deepseek-r1:1.5b
```

### Manual uv Setup

The frontend and backend are separate `uv` projects.

Frontend:

```powershell
cd week_3/frontend
uv sync
uv run uvicorn --app-dir src app:app --host 127.0.0.1 --port 8000
```

Backend:

```powershell
cd week_3/backend
uv sync
uv run uvicorn --app-dir src app:app --host 127.0.0.1 --port 8001
```

When running manually, run Ollama on the host and make sure this URL works:

```text
http://127.0.0.1:11434
```

### Environment Variables

Example environment files are provided at:

- `week_3/frontend/.env.example`
- `week_3/backend/.env.example`

Copy them to `.env` only when you need to override the defaults:

```powershell
Copy-Item week_3/frontend/.env.example week_3/frontend/.env
Copy-Item week_3/backend/.env.example week_3/backend/.env
```

Important frontend variables:

- `BACKEND_URL`: browser-facing chat endpoint. In Compose this is `/api/chat`.
- `BACKEND_INTERNAL_URL`: backend URL used by the frontend proxy. In Compose this is `http://backend:8001/chat`.
- `WEEK1_DB_PATH`: path to the Week 1 jobs SQLite database.

Important backend variables:

- `WEEK2_DB_PATH`: path to the copied Week 2 jobs SQLite database.
- `OLLAMA_HOST`: Ollama server URL.
- `OLLAMA_MODEL`: local model name, default `deepseek-r1:1.5b`.
- `OLLAMA_TIMEOUT_SECONDS`: timeout for local model requests.

Optional Docker secrets wiring is available in `week_3/docker-compose.secrets.yml`. It is not required for the normal local run.

## Usage

### Chat Page

Open:

```text
http://127.0.0.1:8000/chat
```

The chat page supports:

- standard chat without a file
- resume PDF upload
- resume summarization
- skill-gap analysis
- career or learning-path questions

The browser extracts text from selected PDFs using PDF.js before sending the request. The frontend then sends JSON to its own proxy endpoint:

```json
{
  "message": "Analyze my resume",
  "pdf_text": "Extracted resume text..."
}
```

The frontend proxy forwards the request to the backend service. The backend uses the local Ollama model to route the prompt. If the request is about resumes, career readiness, jobs, or skill gaps, it calls the Week 2 `find_skill_gaps()` workflow and then asks Ollama to write the final response. If the request is normal chat, it answers without running skill-gap analysis.

### Dashboard Page

Open:

```text
http://127.0.0.1:8000/dashboard
```

The dashboard reads the Week 1 jobs database and displays:

- total job count
- top companies chart
- job-category distribution chart
- searchable job listings

Search matches job title, company, description, and tech stack.

## API / Function Reference

### Backend Health Check

```http
GET /
```

Returns a simple JSON health response showing that the backend is running.

### Backend Chat Endpoint

```http
POST /chat
```

Request body:

```json
{
  "message": "Find my skills gap",
  "pdf_text": "Optional extracted resume text"
}
```

Response body:

```json
{
  "response": "Human-readable assistant response",
  "gaps": ["aws", "sql"],
  "demand_by_gap": {
    "aws": 5,
    "sql": 3
  },
  "top_demand_gaps": ["aws", "sql"],
  "model": "deepseek-r1:1.5b",
  "error": null,
  "intent": "find_skill_gaps",
  "used_skill_gap_analysis": true
}
```

`intent` can be:

- `chat`
- `find_skill_gaps`
- `clarification`

`used_skill_gap_analysis` is `true` only when the backend routed the request through the Week 2 skill-gap workflow.

### Frontend Proxy Endpoint

```http
POST /api/chat
```

The browser calls this endpoint instead of calling the backend directly. The frontend proxy forwards the same JSON body to the backend URL configured by `BACKEND_INTERNAL_URL`.

### Dashboard JSON Endpoints

```http
GET /api/jobs/summary
GET /api/jobs/search?q=python&limit=25
```

`/api/jobs/summary` returns aggregate chart data. `/api/jobs/search` returns matching job rows from the Week 1 jobs database.

### Important Frontend JavaScript Functions

The chat template contains the browser-side PDF and chat logic:

- `extractPdfText(file)`: reads a selected PDF with PDF.js.
- `buildPageText(items)`: reconstructs page text from PDF text items.
- `normalizeExtractedText(text)`: cleans extracted PDF text before sending it.
- `appendMessage(role, text)`: renders user and assistant messages.
- `getResponseText(data)`: formats backend JSON into readable chat output.
- `sendMessage()`: sends the message and extracted PDF text to the frontend proxy.

## Data / Assumptions

The project uses two SQLite data sources:

- Week 1 dashboard database: `week_1/data/3_gold/jobs.db`
- Copied Week 2 backend database: `week_3/backend/src/week_2/data/jobs_d1.db`

The dashboard reads Week 1 data directly from the frontend service. In Docker Compose, the Week 1 database is mounted read-only into the frontend container.

The backend uses the copied Week 2 runtime so the backend container can run independently of the original Week 2 folder. The original Week 2 files are not modified by Week 3 changes.

Resume PDFs are assumed to contain extractable text. Scanned image-only PDFs may produce empty or low-quality text unless OCR is added later.

The local LLM path is Ollama only. The Week 3 backend does not use Gemini.

## Testing

### Static Checks

Frontend:

```powershell
cd week_3/frontend
uv run --frozen ruff check .
```

Backend:

```powershell
cd week_3/backend
uv run --frozen ruff check .
uv run --frozen python -m py_compile src/app.py src/week_2/find_skill_gaps.py src/week_2/prompt_model.py
```

Compose validation:

```powershell
cd week_3
docker compose config
```

### Manual Backend Test

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8001/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"message":"hello","pdf_text":""}'
```

Expected result: normal chat response, empty gap lists, and `used_skill_gap_analysis` set to `false`.

Skill-gap test:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8001/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"message":"what skills should I improve for backend roles?","pdf_text":""}'
```

Expected result: backend routes to skill-gap analysis and returns structured gap fields.

### Manual Frontend Test

1. Start the Compose stack.
2. Open `http://127.0.0.1:8000/chat`.
3. Send `hello`.
4. Upload a resume PDF and ask `summarize this resume`.
5. Upload a resume PDF and ask `find skills gap`.
6. Confirm the UI shows a useful response instead of crashing when the local model is slow or unavailable.

## Limitations

- Local Ollama performance depends heavily on laptop hardware. The default model can be slow on CPU-only machines.
- The backend includes timeout handling and fallback responses, but long model calls may still take time.
- PDF text extraction does not include OCR for scanned PDFs.
- Chat history is kept only in the browser page and is not persisted.
- The Compose file exposes backend port `8001` for course testing, even though the frontend proxy is the main browser-facing path.
- No authentication or rate limiting is implemented.
- The dashboard categories are keyword-derived from job titles, so they are approximate.

## Architecture Reflection

The Week 3 architecture separates browser-facing UI, backend reasoning, data access, and local model execution.

The frontend owns presentation, PDF extraction, dashboard display, and reverse proxying through `/api/chat`. This keeps the browser pointed at one public service and avoids hardcoding backend container addresses into the client.

The backend owns request routing, skill-gap analysis, and local LLM calls. It uses Ollama for prompt routing and response generation. When a prompt is relevant to resumes, career readiness, or skill gaps, the backend calls the copied Week 2 `find_skill_gaps()` workflow so the Week 3 app still builds on the previous week's function as required.

Docker Compose puts frontend, backend, and Ollama on the same network. The frontend can call `http://backend:8001/chat`, and the backend can call `http://ollama:11434`, while the user mainly interacts with `http://127.0.0.1:8000`.

The main tradeoff is local model reliability. Keeping everything local satisfies the Day 3 bonus requirement, but it makes performance dependent on the user's machine. The fallback paths are designed to keep structured skill-gap output available even when final LLM prose generation is slow.
