from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from week_2.find_skill_gaps import SkillGapResult, find_skill_gaps
from week_2.prompt_model import prompt_model


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = Path(__file__).resolve().parent
DEFAULT_WEEK2_DB_PATH = SRC_DIR / "week_2" / "data" / "jobs_d1.db"
DEFAULT_OLLAMA_MODEL = "deepseek-r1:1.5b"
ROUTE_FIND_SKILL_GAPS = "find_skill_gaps"
ROUTE_CHAT = "chat"
ROUTE_CLARIFICATION = "clarification"
SPACED_TEXT_PATTERN = re.compile(r"\b[A-Za-z0-9](?: [A-Za-z0-9])+\b")
SUMMARY_REQUEST_WORDS = ("summarize", "summary", "describe", "rewrite", "extract")

load_dotenv(BACKEND_ROOT / ".env")


def _load_secret_file_env(env_name: str) -> None:
    secret_path = os.getenv(f"{env_name}_FILE")
    if not secret_path or os.getenv(env_name):
        return

    try:
        secret_value = Path(secret_path).read_text(encoding="utf-8").strip()
    except OSError:
        return

    if secret_value:
        os.environ[env_name] = secret_value


_load_secret_file_env("OLLAMA_HOST")
_load_secret_file_env("OLLAMA_MODEL")

app = FastAPI(title="Week 3 Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = ""
    pdf_text: str = Field(default="")


class ChatResponse(BaseModel):
    response: str
    gaps: list[str]
    demand_by_gap: dict[str, int]
    top_demand_gaps: list[str]
    model: str
    error: str | None = None
    intent: str = ROUTE_FIND_SKILL_GAPS
    used_skill_gap_analysis: bool = True


def _resolve_backend_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path.resolve()


def _week2_db_path() -> Path:
    configured_path = os.getenv("WEEK2_DB_PATH")
    if configured_path:
        return _resolve_backend_path(configured_path)
    return DEFAULT_WEEK2_DB_PATH.resolve()


def _combined_resume_text(payload: ChatRequest) -> str:
    sections = []
    message = payload.message.strip()
    pdf_text = _normalize_pdf_text(payload.pdf_text)

    if message:
        sections.append(f"User message:\n{message}")
    if pdf_text:
        sections.append(f"PDF resume text:\n{pdf_text}")

    return "\n\n".join(sections).strip()


def _normalize_pdf_text(pdf_text: str) -> str:
    normalized = SPACED_TEXT_PATTERN.sub(
        lambda match: match.group(0).replace(" ", ""),
        pdf_text.strip(),
    )
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _build_router_prompt(payload: ChatRequest) -> str:
    message = payload.message.strip() or "(empty)"
    pdf_text = _normalize_pdf_text(payload.pdf_text)
    has_pdf = "yes" if pdf_text else "no"
    return (
        "Reply one word: CHAT or FIND. "
        "CHAT=greeting/general/summarize resume. "
        "FIND=skill gap/job fit/what skills to learn/analyze resume/PDF only. "
        "Examples: hello=>CHAT; summarize resume=>CHAT; find skill gaps=>FIND; "
        "what skills for backend=>FIND. "
        f"Text: {message}. PDF: {has_pdf}"
    )


def _parse_route(response_text: str) -> str | None:
    first_line = next(
        (line.strip().upper() for line in response_text.splitlines() if line.strip()),
        "",
    )
    normalized_line = re.sub(r"[^A-Z_: ]", "", first_line).strip()
    if normalized_line.startswith("ROUTE:"):
        normalized_line = normalized_line.split(":", 1)[1].strip()

    first_token = normalized_line.split()[0] if normalized_line else ""
    if first_token in {"FIND", "FIND_SKILL_GAPS"}:
        return ROUTE_FIND_SKILL_GAPS
    if first_token == "CHAT":
        return ROUTE_CHAT
    return None


def _route_request(payload: ChatRequest, model: str) -> tuple[str, str | None]:
    response_text = prompt_model(model, _build_router_prompt(payload), num_predict=24)
    if response_text.startswith("[Ollama Error]") or response_text.startswith("[Input Error]"):
        return _fallback_route(payload), f"[Ollama Router Error] {response_text}"

    route = _parse_route(response_text)
    if route is None:
        return ROUTE_CLARIFICATION, "[Ollama Router Error] Unable to parse route response."
    return route, None


def _fallback_route(payload: ChatRequest) -> str:
    message = payload.message.casefold()
    has_pdf = bool(_normalize_pdf_text(payload.pdf_text))
    skill_gap_words = (
        "skill",
        "gap",
        "learn",
        "job",
        "career",
        "resume",
        "cv",
        "backend",
        "frontend",
        "developer",
        "data analyst",
        "job fit",
    )

    if any(word in message for word in SUMMARY_REQUEST_WORDS):
        return ROUTE_CHAT if has_pdf else ROUTE_CLARIFICATION
    if has_pdf:
        return ROUTE_FIND_SKILL_GAPS
    if any(word in message for word in skill_gap_words):
        return ROUTE_FIND_SKILL_GAPS
    if message.strip():
        return ROUTE_CHAT
    return ROUTE_CLARIFICATION


def _clarification_response() -> str:
    return (
        "I could not confidently tell whether you want general chat or resume skill-gap analysis. "
        "Please ask again with a resume, PDF text, target role, or a general question."
    )


def _write_temp_resume(resume_text: str) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        prefix="week3_resume_",
        delete=False,
    ) as temp_file:
        temp_file.write(resume_text)
        return Path(temp_file.name)


def _build_chat_prompt(payload: ChatRequest) -> str:
    message = payload.message.strip() or "(empty)"
    pdf_text = _normalize_pdf_text(payload.pdf_text)
    pdf_section = f"\nResume PDF text:\n{pdf_text[:3000]}" if pdf_text else ""
    return (
        "Answer the user directly and completely. "
        "If asked to summarize a resume, summarize only the provided resume text. "
        "If asked to summarize a resume but no resume text is provided, ask the user to upload "
        "or paste the resume. Do not perform skill-gap analysis unless the user asks for it.\n"
        f"User: {message}"
        f"{pdf_section}"
    )


def _is_simple_greeting(message: str) -> bool:
    normalized_message = re.sub(r"[^a-z\s]", " ", message.casefold())
    normalized_message = " ".join(normalized_message.split())
    return normalized_message in {
        "hi",
        "hello",
        "hey",
        "hi there",
        "hello there",
        "hi how are you",
        "hello how are you",
        "how are you",
    }


def _skill_gap_payload(result: SkillGapResult) -> dict:
    ranked_gaps = sorted(
        result.demand_by_gap.items(),
        key=lambda item: (-item[1], item[0]),
    )[:25]
    return {
        "total_gap_count": len(result.gaps),
        "top_gaps_by_demand": [
            {"skill": skill, "matching_jobs": matching_jobs}
            for skill, matching_jobs in ranked_gaps
        ],
        "top_demand_gaps": result.top_demand_gaps,
        "matched_resume_skills": result.matched_resume_skills,
        "error": result.error,
    }


def _build_skill_gap_answer_prompt(payload: ChatRequest, result: SkillGapResult) -> str:
    message = payload.message.strip() or "(empty)"
    pdf_text = _normalize_pdf_text(payload.pdf_text)
    pdf_section = f"\n\nPDF resume text:\n{pdf_text[:8000]}" if pdf_text else ""
    gap_json = json.dumps(_skill_gap_payload(result), ensure_ascii=True, indent=2)
    return (
        "You are a resume skill-gap assistant using a local Ollama model. "
        "Write a helpful answer to the user based on the original request and the structured "
        "Week 2 skill-gap result. Use the resume context when it is present. "
        "Use only the provided skill-gap JSON for missing skills, demand counts, and top gaps. "
        "Do not invent job counts, skills, or resume experience. If the resume is not technical, "
        "explain that tactfully and frame the gaps as a transition path. If there is no resume, "
        "say the advice is based on the job database and target role only. "
        "Do not output JSON. Make the answer actionable and complete.\n\n"
        f"User message:\n{message}"
        f"{pdf_section}\n\n"
        f"Skill-gap JSON:\n{gap_json}"
    )


def _model_failure_response(result: SkillGapResult) -> str:
    if not result.gaps:
        return (
            "The local model could not finish writing the response, and no skill gaps were found "
            "from the current input."
        )

    ranked_gaps = sorted(
        result.demand_by_gap.items(),
        key=lambda item: (-item[1], item[0]),
    )
    gap_list = " - ".join(skill for skill, _count in ranked_gaps)
    return f"Skills gap identified: - {gap_list}"


def _combine_errors(*errors: str | None) -> str | None:
    unique_errors = [error for error in dict.fromkeys(errors) if error]
    return "; ".join(unique_errors) or None


@app.get("/")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "week-3-backend"}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    resume_text = _combined_resume_text(payload)
    model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    if not resume_text:
        return ChatResponse(
            response=_clarification_response(),
            gaps=[],
            demand_by_gap={},
            top_demand_gaps=[],
            model=model,
            error=None,
            intent=ROUTE_CLARIFICATION,
            used_skill_gap_analysis=False,
        )

    route, route_error = _route_request(payload, model)
    if route == ROUTE_CLARIFICATION:
        return ChatResponse(
            response=_clarification_response(),
            gaps=[],
            demand_by_gap={},
            top_demand_gaps=[],
            model=model,
            error=route_error,
            intent=ROUTE_CLARIFICATION,
            used_skill_gap_analysis=False,
        )

    if route == ROUTE_CHAT:
        chat_error = None
        response = prompt_model(model, _build_chat_prompt(payload))
        if response.startswith("[Ollama Error]") or response.startswith("[Input Error]"):
            chat_error = response
            if _is_simple_greeting(payload.message):
                response = (
                    "The local model did not respond, so this is the fallback reply. "
                    "I can chat normally, summarize a pasted or uploaded resume, "
                    "or analyze skill gaps from a resume once Ollama is ready."
                )
            else:
                response = "The local model could not answer that chat request."

        return ChatResponse(
            response=response,
            gaps=[],
            demand_by_gap={},
            top_demand_gaps=[],
            model=model,
            error=_combine_errors(route_error, chat_error),
            intent=ROUTE_CHAT,
            used_skill_gap_analysis=False,
        )

    db_path = _week2_db_path()
    temp_resume_path = _write_temp_resume(resume_text)
    try:
        skill_gap_result = find_skill_gaps(str(temp_resume_path), str(db_path))
    finally:
        temp_resume_path.unlink(missing_ok=True)

    explanation = prompt_model(
        model,
        _build_skill_gap_answer_prompt(payload, skill_gap_result),
    )
    answer_error = None
    if explanation.startswith("[Ollama Error]") or explanation.startswith("[Input Error]"):
        answer_error = explanation
        explanation = _model_failure_response(skill_gap_result)

    return ChatResponse(
        response=explanation,
        gaps=skill_gap_result.gaps,
        demand_by_gap=skill_gap_result.demand_by_gap,
        top_demand_gaps=skill_gap_result.top_demand_gaps,
        model=model,
        error=_combine_errors(route_error, skill_gap_result.error, answer_error),
        intent=ROUTE_FIND_SKILL_GAPS,
        used_skill_gap_analysis=True,
    )
