import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field


FRONTEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BACKEND_URL = "/api/chat"
DEFAULT_BACKEND_INTERNAL_URL = "http://127.0.0.1:8001/chat"
DEFAULT_WEEK1_DB_PATH = REPO_ROOT / "week_1" / "data" / "3_gold" / "jobs.db"
TOP_COMPANY_LIMIT = 8
BACKEND_TIMEOUT_SECONDS = 180

load_dotenv(FRONTEND_DIR / ".env")

app = FastAPI()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class ChatRequest(BaseModel):
    message: str = ""
    pdf_text: str = Field(default="")


def _resolve_week1_db_path() -> Path:
    configured_path = os.getenv("WEEK1_DB_PATH")
    if configured_path:
        path = Path(configured_path).expanduser()
        if not path.is_absolute():
            path = FRONTEND_DIR / path
        return path.resolve()

    return DEFAULT_WEEK1_DB_PATH


def _backend_proxy_url() -> str:
    configured_internal_url = os.getenv("BACKEND_INTERNAL_URL")
    if configured_internal_url:
        return configured_internal_url

    configured_browser_url = os.getenv("BACKEND_URL", "")
    if configured_browser_url.startswith(("http://", "https://")):
        return configured_browser_url

    return DEFAULT_BACKEND_INTERNAL_URL


def _post_backend_chat(payload: ChatRequest) -> dict[str, Any]:
    request = urllib.request.Request(
        _backend_proxy_url(),
        data=payload.model_dump_json().encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=BACKEND_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
            content_type = response.headers.get("content-type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=502,
            detail=f"Backend returned HTTP {exc.code}: {detail}",
        ) from exc
    except urllib.error.URLError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Backend is unavailable: {exc.reason}",
        ) from exc

    if "application/json" in content_type:
        parsed_body = json.loads(body)
        if isinstance(parsed_body, dict):
            return parsed_body
        return {"response": parsed_body}

    return {"response": body}


def _connect_to_jobs_db() -> sqlite3.Connection:
    db_path = _resolve_week1_db_path()
    if not db_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Week 1 database not found at {db_path}",
        )

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _description_excerpt(description: object, max_length: int = 220) -> str:
    text = _clean_text(description)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _categorize_job_title(job_title: object) -> str:
    title = _clean_text(job_title).casefold()

    if any(keyword in title for keyword in ("ai", "machine learning", "gen ai", "llm")):
        return "AI / ML"
    if "data" in title or "analytics" in title or "analyst" in title:
        return "Data"
    if "backend" in title or "back-end" in title:
        return "Backend"
    if "qa" in title or "test" in title or "tester" in title:
        return "QA / Testing"
    if "automation" in title or "workflow" in title:
        return "Automation"
    if "support" in title or "administrator" in title or "admin" in title:
        return "Support / Admin"
    if "software" in title or "developer" in title or "engineer" in title:
        return "Software"
    return "Other"


def _fetch_top_companies(connection: sqlite3.Connection) -> dict[str, list[object]]:
    rows = connection.execute(
        """
        SELECT company, COUNT(*) AS count
        FROM jobs
        WHERE COALESCE(company, '') <> ''
        GROUP BY company
        ORDER BY count DESC, company ASC
        """,
    ).fetchall()

    top_rows = rows[:TOP_COMPANY_LIMIT]
    other_count = sum(int(row["count"]) for row in rows[TOP_COMPANY_LIMIT:])
    labels = [_clean_text(row["company"]) for row in top_rows]
    counts = [int(row["count"]) for row in top_rows]

    if other_count:
        labels.append("Other")
        counts.append(other_count)

    return {"labels": labels, "counts": counts}


def _fetch_job_distribution(connection: sqlite3.Connection) -> dict[str, list[object]]:
    categories = {
        "AI / ML": 0,
        "Data": 0,
        "Backend": 0,
        "Software": 0,
        "QA / Testing": 0,
        "Automation": 0,
        "Support / Admin": 0,
        "Other": 0,
    }

    rows = connection.execute("SELECT job_title FROM jobs").fetchall()
    for row in rows:
        categories[_categorize_job_title(row["job_title"])] += 1

    return {
        "labels": list(categories.keys()),
        "counts": list(categories.values()),
    }


@app.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="landing_page.html",
        context={},
    )


@app.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="chat_page.html",
        context={
            "backend_url": os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL),
        },
    )


@app.post("/api/chat")
def chat_proxy(payload: ChatRequest) -> dict[str, Any]:
    return _post_backend_chat(payload)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={},
    )


@app.get("/api/jobs/summary")
def jobs_summary() -> dict[str, object]:
    with _connect_to_jobs_db() as connection:
        total_jobs = int(connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
        total_companies = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT company)
                FROM jobs
                WHERE COALESCE(company, '') <> ''
                """,
            ).fetchone()[0]
        )
        top_company_row = connection.execute(
            """
            SELECT company, COUNT(*) AS count
            FROM jobs
            WHERE COALESCE(company, '') <> ''
            GROUP BY company
            ORDER BY count DESC, company ASC
            LIMIT 1
            """,
        ).fetchone()

        top_company = None
        if top_company_row is not None:
            top_company = {
                "name": _clean_text(top_company_row["company"]),
                "count": int(top_company_row["count"]),
            }

        return {
            "total_jobs": total_jobs,
            "total_companies": total_companies,
            "top_company": top_company,
            "database_path": str(_resolve_week1_db_path()),
            "charts": {
                "top_companies": _fetch_top_companies(connection),
                "job_distribution": _fetch_job_distribution(connection),
            },
        }


@app.get("/api/jobs/search")
def search_jobs(
    q: str = "",
    limit: int = Query(default=25, ge=1, le=50),
) -> dict[str, object]:
    search_term = f"%{q.strip()}%"
    sql = """
        SELECT source_id, job_title, company, description, tech_stack, quality
        FROM jobs
    """
    parameters: tuple[object, ...] = ()

    if q.strip():
        sql += """
            WHERE job_title LIKE ?
               OR company LIKE ?
               OR description LIKE ?
               OR tech_stack LIKE ?
        """
        parameters = (search_term, search_term, search_term, search_term)

    sql += " ORDER BY job_title ASC, company ASC LIMIT ?"
    parameters = (*parameters, limit)

    with _connect_to_jobs_db() as connection:
        rows = connection.execute(sql, parameters).fetchall()

    return {
        "query": q,
        "count": len(rows),
        "jobs": [
            {
                "source_id": _clean_text(row["source_id"]),
                "job_title": _clean_text(row["job_title"]) or "Untitled role",
                "company": _clean_text(row["company"]) or "Unknown company",
                "tech_stack": _clean_text(row["tech_stack"]),
                "quality": _clean_text(row["quality"]),
                "description_excerpt": _description_excerpt(row["description"]),
            }
            for row in rows
        ],
    }
