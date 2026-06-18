from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_URL = "data/jobs_d1.db"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_BATCH_SIZE = 3
DEFAULT_MAX_RETRIES = 3
RATE_LIMITS_PATH = BASE_DIR / "rate_limits.txt"
DB_SERVER_PATH = BASE_DIR / "db_server.py"
QUERY_DIR = BASE_DIR / "queries"

SOFT_SKILLS = {
    "adaptability",
    "analytical thinking",
    "attention to detail",
    "collaboration",
    "communication",
    "critical thinking",
    "leadership",
    "management",
    "mentoring",
    "presentation",
    "problem solving",
    "stakeholder management",
    "teamwork",
    "time management",
}

TECH_HINTS = {
    "abap",
    "api",
    "apis",
    "aws",
    "azure",
    "ci/cd",
    "cloud",
    "data",
    "database",
    "datastudio",
    "devops",
    "etl",
    "excel",
    "gcp",
    "git",
    "java",
    "javascript",
    "kubernetes",
    "linux",
    "llm",
    "machine learning",
    "mongodb",
    "mysql",
    "oracle",
    "powerbi",
    "python",
    "r",
    "sql",
    "tableau",
    "tensorflow",
    "testing",
}

SECTION_HINTS = (
    "technical skills",
    "requirements",
    "qualifications",
    "responsibilities",
    "experience",
    "tools",
    "technologies",
    "stack",
    "proficient",
    "knowledge",
    "programming",
)

FALLBACK_TECH_PATTERNS = (
    ("Enterprise application development", r"enterprise application development"),
    ("Application maintenance", r"application[s]? .*maintenance|maintenance .*application"),
    ("Programming", r"programming"),
    ("Software development", r"software|development"),
    ("Development methodologies", r"development methodolog"),
    ("Requirements gathering", r"requirements gathering"),
    ("System design", r"\bdesign\b"),
    ("Testing", r"\btesting\b"),
    ("Deployment", r"\bdeployment\b"),
    ("Data gathering", r"data gathering"),
    ("System troubleshooting", r"system .*problem|problem analysis|resolution of system"),
)


class JobRecord(BaseModel):
    source_id: str
    job_title: str
    company: str
    description: str


class TagDataResult(BaseModel):
    rows_updated: int = 0
    tokens: int = 0
    time_ms: float = 0.0
    duplicate_count: int = 0
    direct_match_percentage: float = 0.0
    empty_output_count: int = 0
    failed_rows: list[str] = Field(default_factory=list)


class BatchTagResult(BaseModel):
    source_id: str
    tech_stack: list[str] = Field(default_factory=list)


def tag_data(db_url: str):
    """Populate missing jobs.tech_stack values and return tokens and elapsed milliseconds."""
    result = _run_async(_tag_data_async(db_url, DEFAULT_MODEL, DEFAULT_BATCH_SIZE))
    return result.tokens, result.time_ms


def _run_async(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 - CLI must not expose stack traces.
        print(f"[Tagging Error] {exc}")
        return TagDataResult()


async def _tag_data_async(
    db_url: str,
    model: str,
    batch_size: int,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> TagDataResult:
    started = time.perf_counter()
    failed_rows: list[str] = []
    rows_updated = 0
    tokens_used = 0
    duplicate_count = 0
    empty_output_count = 0
    direct_matches = 0
    stored_skill_count = 0

    try:
        from fastmcp import Client
    except ImportError as exc:
        print(f"[Dependency Error] Missing package: {exc.name}")
        return TagDataResult(time_ms=_elapsed_ms(started))

    db_path = _resolve_db_path(db_url)
    os.environ["TAG_DATA_DB_PATH"] = str(db_path)
    async with Client(str(DB_SERVER_PATH)) as mcp_client:
        count_result = await _query_db(mcp_client, "count_missing_tech_stack.sql")
        missing_count = int(count_result["rows"][0]["missing_count"])
        if missing_count == 0:
            result = TagDataResult(time_ms=_elapsed_ms(started))
            print("No data to tag")
            _print_total(result)
            return result

        requests_per_minute, requests_per_day = _read_model_rate_limits(model)
        retry_delay_seconds = calculate_retry_delay_seconds(requests_per_minute)
        selected_batch_size = calculate_batch_size(
            total_rows=missing_count,
            requests_per_day=requests_per_day,
            reliability_floor=batch_size,
        )

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("[Gemini Error] Missing GEMINI_API_KEY or GOOGLE_API_KEY environment variable.")
            return TagDataResult(time_ms=_elapsed_ms(started))

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            print(f"[Dependency Error] Missing package: {exc.name}")
            return TagDataResult(time_ms=_elapsed_ms(started))

        gemini = genai.Client(api_key=api_key)

        fetch_result = await _query_db(
            mcp_client,
            "select_missing_tech_stack.sql",
            {"limit": missing_count},
        )
        raw_jobs = fetch_result["rows"]
        jobs = [JobRecord.model_validate(job) for job in raw_jobs]
        display_numbers = {job.source_id: index for index, job in enumerate(jobs, start=1)}

        for batch_index, batch in enumerate(_chunks(jobs, selected_batch_size)):
            tagged_rows, token_count = await _tag_batch_with_fallback(
                batch_index=batch_index,
                batch=batch,
                model=model,
                gemini=gemini,
                types=types,
                retry_delay_seconds=retry_delay_seconds,
                max_retries=max_retries,
            )
            tokens_used += token_count

            if not tagged_rows:
                failed_rows.extend(job.source_id for job in batch)
                continue

            updates: list[dict[str, str]] = []
            jobs_by_id = {job.source_id: job for job in batch}
            for tagged_row in tagged_rows:
                job = jobs_by_id[tagged_row.source_id]
                skills, duplicates = _normalize_skills(tagged_row.tech_stack)
                duplicate_count += duplicates
                if not skills:
                    empty_output_count += 1
                    skills = _fallback_skills_from_description(job) or ["Not specified"]

                tech_stack = ", ".join(skills)
                updates.append(
                    {
                        "source_id": tagged_row.source_id,
                        "tech_stack": tech_stack,
                        "display_index": str(display_numbers[tagged_row.source_id]),
                    }
                )
                direct_matches += _count_direct_matches(skills, job.description)
                stored_skill_count += len(skills)

            if not updates:
                continue

            update_result = await _query_db(
                mcp_client,
                "update_tech_stack.sql",
                [
                    {
                        "source_id": update["source_id"],
                        "tech_stack": update["tech_stack"],
                    }
                    for update in updates
                ],
            )
            updated_count = int(update_result["rowcount"])
            rows_updated += updated_count
            for update in updates:
                display_index = update.get("display_index", update["source_id"])
                print(f"Analyzed Job {display_index}: {update['tech_stack']}")

    direct_match_percentage = (
        round((direct_matches / stored_skill_count) * 100, 2) if stored_skill_count else 0.0
    )
    result = TagDataResult(
        rows_updated=rows_updated,
        tokens=tokens_used,
        time_ms=_elapsed_ms(started),
        duplicate_count=duplicate_count,
        direct_match_percentage=direct_match_percentage,
        empty_output_count=empty_output_count,
        failed_rows=failed_rows,
    )
    _print_summary(result, jobs, selected_batch_size)
    return result


async def _tag_batch_with_fallback(
    batch_index: int,
    batch: list[JobRecord],
    model: str,
    gemini: Any,
    types: Any,
    retry_delay_seconds: int,
    max_retries: int,
) -> tuple[list[BatchTagResult], int]:
    tagged_rows, tokens = await _try_tag_batch(
        batch_index=batch_index,
        batch=batch,
        model=model,
        gemini=gemini,
        types=types,
        retry_delay_seconds=retry_delay_seconds,
        max_retries=max_retries,
    )
    if tagged_rows:
        return tagged_rows, tokens

    if len(batch) == 1:
        fallback_skills = _fallback_skills_from_description(batch[0])
        if fallback_skills:
            print(f"[Batch {batch_index}] Using grounded fallback for Job {batch[0].source_id}")
        else:
            fallback_skills = ["Not specified"]
        return [
            BatchTagResult(
                source_id=batch[0].source_id,
                tech_stack=fallback_skills,
            )
        ], tokens

    fallback_rows: list[BatchTagResult] = []
    fallback_tokens = tokens
    for offset, job in enumerate(batch):
        row_results, row_tokens = await _tag_batch_with_fallback(
            batch_index=batch_index,
            batch=[job],
            model=model,
            gemini=gemini,
            types=types,
            retry_delay_seconds=retry_delay_seconds,
            max_retries=max_retries,
        )
        fallback_rows.extend(row_results)
        fallback_tokens += row_tokens
    return fallback_rows, fallback_tokens


async def _try_tag_batch(
    batch_index: int,
    batch: list[JobRecord],
    model: str,
    gemini: Any,
    types: Any,
    retry_delay_seconds: int,
    max_retries: int,
    label: str | None = None,
) -> tuple[list[BatchTagResult], int]:
    batch_label = label or str(batch_index)
    prompt = _build_optimized_prompt(batch)
    total_tokens = 0

    for attempt in range(1, max_retries + 1):
        try:
            response = gemini.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            response_text = getattr(response, "text", "") or ""
            total_tokens += _response_token_count(response, prompt, response_text)
            tagged_rows = _parse_batch_response(response_text, batch)
            return tagged_rows, total_tokens
        except Exception as exc:  # noqa: BLE001 - retry and continue without stack traces.
            print(f"[Batch {batch_label}] Attempt {attempt} failed: {exc}")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay_seconds)

    return [], total_tokens


def _build_baseline_prompt(batch: list[JobRecord]) -> str:
    descriptions = "\n\n".join(
        f"Job ID: {job.source_id}\nTitle: {job.job_title}\nCompany: {job.company}\nDescription:\n{job.description}"
        for job in batch
    )
    return (
        "Analyze each job description and identify every technical stack, programming "
        "language, framework, database, cloud platform, analytics tool, engineering "
        "practice, and technical process mentioned. Return comma-separated skills for "
        "each job. Avoid soft skills.\n\n"
        f"{descriptions}"
    )


def _build_optimized_prompt(batch: list[JobRecord]) -> str:
    jobs_payload = [
        {
            "source_id": job.source_id,
            "title": job.job_title,
            "description_excerpt": _compact_description(job.description),
        }
        for job in batch
    ]
    return (
        "Return only JSON. Extract technical skills/stacks from each job. "
        "Include tools, languages, frameworks, databases, cloud, ML/data methods, "
        "testing, CI/CD, APIs, and data platforms. Exclude soft skills like leadership, "
        "communication, teamwork, and management. Use concise skill names. Schema: "
        '[{"source_id":"...","tech_stack":["Python","SQL"]}]\n'
        f"Jobs: {json.dumps(jobs_payload, ensure_ascii=True)}"
    )


def _compact_description(description: str, max_chars: int = 1800) -> str:
    text = re.sub(r"\s+", " ", description).strip()
    if len(text) <= max_chars:
        return text

    parts = re.split(r"(?<=[.!?])\s+|\s+(?=Track \d+:)|\s+(?=Technical Skills)", text)
    scored: list[tuple[int, int, str]] = []
    for index, part in enumerate(parts):
        lowered = part.lower()
        score = sum(4 for hint in SECTION_HINTS if hint in lowered)
        score += sum(1 for hint in TECH_HINTS if hint in lowered)
        if score:
            scored.append((score, -index, part.strip()))

    selected: list[str] = []
    total_chars = 0
    for _, _, part in sorted(scored, reverse=True):
        if not part:
            continue
        if total_chars + len(part) > max_chars:
            continue
        selected.append(part)
        total_chars += len(part)

    if not selected:
        return text[:max_chars].rstrip()

    compacted = " ".join(selected)
    return compacted[:max_chars].rstrip()


def _parse_batch_response(response_text: str, batch: list[JobRecord]) -> list[BatchTagResult]:
    payload = _load_json_array(response_text)
    results = [BatchTagResult.model_validate(item) for item in payload]
    expected_ids = {job.source_id for job in batch}
    actual_ids = {result.source_id for result in results}
    if actual_ids != expected_ids:
        raise ValueError("Mismatch between batch size and response")
    empty_ids = [result.source_id for result in results if not result.tech_stack]
    if empty_ids:
        raise ValueError(f"Empty tech_stack for source_id(s): {', '.join(empty_ids)}")
    return results


def _load_json_array(text: str) -> list[Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    if not cleaned.startswith("["):
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Gemini response did not contain a JSON array")
        cleaned = cleaned[start : end + 1]
    payload = json.loads(cleaned)
    if not isinstance(payload, list):
        raise ValueError("Gemini response JSON is not a list")
    return payload


def _normalize_skills(raw_skills: list[str]) -> tuple[list[str], int]:
    normalized: list[str] = []
    seen: set[str] = set()
    duplicates = 0

    for raw_skill in raw_skills:
        for candidate in str(raw_skill).split(","):
            skill = _clean_skill(candidate)
            if not skill:
                continue
            skill_key = skill.lower()
            if skill_key in SOFT_SKILLS:
                continue
            if skill_key in seen:
                duplicates += 1
                continue
            seen.add(skill_key)
            normalized.append(skill)

    return normalized, duplicates


def _clean_skill(skill: str) -> str:
    cleaned = re.sub(r"\s+", " ", skill).strip(" -;:.\t\n\r")
    cleaned = cleaned.replace("Power BI", "PowerBI")
    cleaned = cleaned.replace("Data Studio", "DataStudio")
    if len(cleaned) < 2:
        return ""
    return cleaned


def _fallback_skills_from_description(job: JobRecord) -> list[str]:
    """Grounded last-resort extractor so a valid job row is not left NULL."""
    text = f"{job.job_title} {job.description}".lower()
    skills: list[str] = []
    seen: set[str] = set()
    for skill, pattern in FALLBACK_TECH_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE) and skill.lower() not in seen:
            skills.append(skill)
            seen.add(skill.lower())
    return skills


def _count_direct_matches(skills: list[str], description: str) -> int:
    lowered_description = description.lower()
    return sum(1 for skill in skills if skill.lower() in lowered_description)


def _response_token_count(response: Any, prompt: str, response_text: str) -> int:
    usage = getattr(response, "usage_metadata", None)
    total = getattr(usage, "total_token_count", None) if usage else None
    if isinstance(total, int) and total > 0:
        return total
    return _estimate_tokens(prompt) + _estimate_tokens(response_text)


def _estimate_tokens(text: str) -> int:
    words = re.findall(r"\S+", text)
    return len(words) * 4


def calculate_retry_delay_seconds(requests_per_minute: int) -> int:
    """Calculate the minimum spacing between requests from the RPM limit."""
    if requests_per_minute <= 0:
        raise ValueError("requests_per_minute must be greater than zero")
    return math.ceil(60 / requests_per_minute)


def calculate_batch_size(
    total_rows: int,
    requests_per_day: int,
    reliability_floor: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Meet the daily limit while retaining a small, reliable JSON batch size."""
    if total_rows < 0:
        raise ValueError("total_rows cannot be negative")
    if requests_per_day <= 0:
        raise ValueError("requests_per_day must be greater than zero")
    if reliability_floor <= 0:
        raise ValueError("reliability_floor must be greater than zero")

    minimum_batch_size_for_daily_limit = math.ceil(total_rows / requests_per_day)
    return max(minimum_batch_size_for_daily_limit, reliability_floor)


def _read_model_rate_limits(model: str) -> tuple[int, int]:
    if not RATE_LIMITS_PATH.exists():
        raise FileNotFoundError(f"Rate-limit file not found: {RATE_LIMITS_PATH}")

    for line in RATE_LIMITS_PATH.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == model:
            requests_per_minute = int(_parse_quantity(parts[1]))
            requests_per_day = int(_parse_quantity(parts[3]))
            return requests_per_minute, requests_per_day

    raise ValueError(f"No rate limits configured for model: {model}")


def _parse_quantity(value: str) -> float:
    value = value.strip().upper()
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    suffix = value[-1]
    if suffix in multipliers:
        return float(value[:-1]) * multipliers[suffix]
    return float(value)


def _resolve_db_path(db_url: str) -> Path:
    db_path = Path(db_url)
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    return db_path.resolve()


def _read_query(name: str) -> str:
    return (QUERY_DIR / name).read_text(encoding="utf-8")


async def _query_db(
    client: Any,
    query_name: str,
    parameters: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {"sql_query": _read_query(query_name)}
    if parameters is not None:
        arguments["parameters"] = parameters
    result = await _call_tool(client, "query_db", arguments)
    if not isinstance(result, dict) or "rows" not in result or "rowcount" not in result:
        raise ValueError(f"Invalid query_db response for {query_name}")
    return result


def _chunks(items: list[JobRecord], size: int) -> list[list[JobRecord]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


async def _call_tool(client: Any, name: str, arguments: dict[str, Any]) -> Any:
    result = await client.call_tool(name, arguments)
    return _extract_tool_data(result)


def _extract_tool_data(result: Any) -> Any:
    data = getattr(result, "data", None)
    if data is not None:
        return data

    structured_content = getattr(result, "structured_content", None)
    if structured_content is not None:
        if isinstance(structured_content, dict) and "result" in structured_content:
            return structured_content["result"]
        return structured_content

    content = getattr(result, "content", None)
    if content:
        first = content[0]
        text = getattr(first, "text", str(first))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    return result


def _percentage_reduction(before: int, after: int) -> float:
    if before <= 0:
        return 0.0
    return round(((before - after) / before) * 100, 2)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _print_total(result: TagDataResult) -> None:
    print(f"Total tokens used: {result.tokens}, took {result.time_ms}ms")


def _prompt_optimization_stats(
    jobs: list[JobRecord],
    batch_size: int,
) -> tuple[int, int, float]:
    baseline_tokens = sum(_estimate_tokens(_build_baseline_prompt([job])) for job in jobs)
    optimized_tokens = sum(
        _estimate_tokens(_build_optimized_prompt(batch))
        for batch in _chunks(jobs, batch_size)
    )
    return baseline_tokens, optimized_tokens, _percentage_reduction(
        baseline_tokens,
        optimized_tokens,
    )


def _print_summary(result: TagDataResult, jobs: list[JobRecord], batch_size: int) -> None:
    row_count = len(jobs)
    per_row_calls = row_count
    batched_calls = math.ceil(row_count / batch_size) if row_count else 0
    call_reduction = _percentage_reduction(per_row_calls, batched_calls)
    baseline_tokens, optimized_tokens, prompt_reduction = _prompt_optimization_stats(
        jobs,
        batch_size,
    )

    print(f"Rows updated: {result.rows_updated}")
    print(f"Duplicate skills removed: {result.duplicate_count}")
    print(f"Direct match percentage: {result.direct_match_percentage:.2f}%")
    print(f"Empty outputs: {result.empty_output_count}")
    print(
        "Prompt optimization proof: estimated prompt tokens "
        f"{baseline_tokens} -> {optimized_tokens} "
        f"({prompt_reduction:.2f}% reduction)"
    )
    print(
        "Time optimization proof: planned Gemini calls "
        f"{per_row_calls} -> {batched_calls} "
        f"({call_reduction:.2f}% reduction)"
    )
    if result.failed_rows:
        print(f"Failed rows: {', '.join(result.failed_rows)}")
    _print_total(result)


def main() -> None:
    tag_data(DEFAULT_DB_URL)


if __name__ == "__main__":
    main()