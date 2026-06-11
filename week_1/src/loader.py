import hashlib
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


DB_NAME = "jobs.db"
QUERY_DIR = Path(__file__).resolve().parents[1] / "queries"

GOLD_ICON = "\U0001f947"
WARNING_ICON = "\u26a0\ufe0f"
SUCCESS_ICON = "\u2705"
SKIPPED_ICON = "\u23ed\ufe0f"
SUMMARY_ICON = "\U0001f4ca"

REQUIRED_FIELDS = ("source_id", "job_title", "company", "description")

LoadStatus = Literal["inserted", "updated", "skipped", "failed"]


@dataclass(frozen=True)
class LoadResult:
    source_path: Path
    status: LoadStatus
    reason: str | None = None


def _configure_stdout() -> None:
    if not hasattr(sys.stdout, "reconfigure"):
        return

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except OSError:
        return
    except ValueError:
        return


def _iter_json_files(input_path: Path) -> list[Path]:
    if not input_path.exists() or not input_path.is_dir():
        return []

    return sorted(
        (
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".json"
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )


def _read_query(file_name: str) -> str:
    return (QUERY_DIR / file_name).read_text(encoding="utf-8")


def _get_job_columns(connection: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in connection.execute("PRAGMA table_info(jobs)")}


def _ensure_database_schema(connection: sqlite3.Connection) -> None:
    connection.execute(_read_query("create_jobs_table.sql"))

    columns = _get_job_columns(connection)
    if "content_hash" not in columns:
        connection.execute(_read_query("add_content_hash_column.sql"))
    if "quality" not in columns:
        connection.execute(_read_query("add_quality_column.sql"))

    connection.execute(_read_query("create_jobs_quarantine_table.sql"))
    connection.commit()


def _clean_field(value: object) -> str:
    if not isinstance(value, str):
        return ""

    return " ".join(value.split())


def _read_job_json(json_path: Path) -> dict[str, str]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object.")

    description = data.get("description", "")
    if not isinstance(description, str):
        description = ""

    cleaned_data = {
        "source_id": _clean_field(data.get("source_id", "")),
        "job_title": _clean_field(data.get("job_title", "")),
        "company": _clean_field(data.get("company", "")),
        "description": description.strip(),
    }
    missing_fields = [
        field_name
        for field_name, value in cleaned_data.items()
        if not _clean_field(value)
    ]
    if missing_fields:
        raise ValueError(f"Missing {', '.join(missing_fields)}.")

    return cleaned_data


def _normalize_hash_value(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _compute_content_hash(data: dict[str, str]) -> str:
    hash_input = "|".join(
        _normalize_hash_value(data[field_name])
        for field_name in ("job_title", "company", "description")
    )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def _fetch_existing_content_hash(
    connection: sqlite3.Connection,
    source_id: str,
) -> str | None:
    row = connection.execute(
        _read_query("select_existing_content_hash.sql"),
        (source_id,),
    ).fetchone()
    if row is None:
        return None

    return str(row[0] or "")


def _insert_job(
    connection: sqlite3.Connection,
    data: dict[str, str],
    content_hash: str,
) -> None:
    connection.execute(
        _read_query("insert_job.sql"),
        (
            data["source_id"],
            data["job_title"],
            data["company"],
            data["description"],
            "",
            content_hash,
            "",
        ),
    )


def _update_job(
    connection: sqlite3.Connection,
    data: dict[str, str],
    content_hash: str,
) -> None:
    connection.execute(
        _read_query("update_job.sql"),
        (
            data["job_title"],
            data["company"],
            data["description"],
            "",
            content_hash,
            data["source_id"],
        ),
    )


def _upsert_job(connection: sqlite3.Connection, data: dict[str, str]) -> LoadStatus:
    content_hash = _compute_content_hash(data)
    existing_hash = _fetch_existing_content_hash(connection, data["source_id"])

    if existing_hash is None:
        _insert_job(connection, data, content_hash)
        return "inserted"

    if existing_hash == content_hash:
        return "skipped"

    _update_job(connection, data, content_hash)
    return "updated"


def load_json(json_path: Path, connection: sqlite3.Connection) -> LoadResult:
    try:
        data = _read_job_json(json_path)
        status = _upsert_job(connection, data)
    except Exception as error:
        return LoadResult(json_path, "failed", str(error))

    if status == "skipped":
        return LoadResult(json_path, status, "unchanged")

    return LoadResult(json_path, status)


def _log_result(result: LoadResult) -> None:
    if result.status == "inserted":
        logging.info("%s Inserted: %s", SUCCESS_ICON, result.source_path.name)
    elif result.status == "updated":
        logging.info("%s Updated: %s", SUCCESS_ICON, result.source_path.name)
    elif result.status == "skipped":
        logging.info("%s Skipped (unchanged): %s", SKIPPED_ICON, result.source_path.name)
    else:
        reason = result.reason or "unknown reason"
        logging.error("%s Failed: %s (%s)", WARNING_ICON, result.source_path.name, reason)


def _print_summary(results: list[LoadResult]) -> None:
    total = len(results)
    inserted = sum(result.status == "inserted" for result in results)
    updated = sum(result.status == "updated" for result in results)
    skipped = total - inserted - updated

    print(f"\n{SUMMARY_ICON} Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Updated: {updated} | Skipped: {skipped}")


def load_all_jsons(input_dir, output_dir) -> None:
    _configure_stdout()

    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    db_path = output_path / DB_NAME

    print(f"{GOLD_ICON} Gold: Loading JSON files...")

    if not input_path.exists():
        logging.warning("%s Source directory not found: %s", WARNING_ICON, input_path)
    elif not input_path.is_dir():
        logging.warning("%s Source path is not a directory: %s", WARNING_ICON, input_path)

    json_files = _iter_json_files(input_path)
    results: list[LoadResult] = []

    with sqlite3.connect(db_path) as connection:
        _ensure_database_schema(connection)
        for json_path in json_files:
            result = load_json(json_path, connection)
            results.append(result)
            _log_result(result)
        connection.commit()

    _print_summary(results)
