import logging
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path


REPORT_ICON = "\U0001f50d"
CHART_ICON = "\U0001f4c8"
QUESTION_ICON = "\u2753"
NOTE_ICON = "\U0001f4dd"
WARNING_ICON = "\u26a0\ufe0f"
ALERT_ICON = "\U0001f6a8"
ERROR_ICON = "\u274c"
SUCCESS_ICON = "\u2705"
QUERY_DIR = Path(__file__).resolve().parents[1] / "queries"
PROFILE_COLUMNS = {"job_title", "company", "description"}
EXTREME_ORDERS = {"ASC", "DESC"}
REPEATED_SPECIALS = re.compile(r"[!#$%*@]{4,}")


@dataclass(frozen=True)
class ExtremeDescription:
    source_id: str
    job_title: str
    description_length: int


@dataclass(frozen=True)
class DataProfile:
    total_records: int
    missing_job_title: int
    missing_company: int
    missing_description: int
    average_description_length: int
    shortest_description: ExtremeDescription | None
    longest_description: ExtremeDescription | None


@dataclass(frozen=True)
class LowQualityJob:
    source_id: str
    job_title: str
    company: str
    description_length: int


def _configure_stdout() -> None:
    if not hasattr(sys.stdout, "reconfigure"):
        return

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except OSError:
        return
    except ValueError:
        return


def _read_query(file_name: str) -> str:
    return (QUERY_DIR / file_name).read_text(encoding="utf-8")


def _get_job_columns(connection: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in connection.execute("PRAGMA table_info(jobs)")}


def _ensure_profile_schema(connection: sqlite3.Connection) -> None:
    connection.execute(_read_query("create_jobs_table.sql"))

    columns = _get_job_columns(connection)
    if "content_hash" not in columns:
        connection.execute(_read_query("add_content_hash_column.sql"))
    if "quality" not in columns:
        connection.execute(_read_query("add_quality_column.sql"))

    connection.execute(_read_query("create_jobs_quarantine_table.sql"))
    connection.commit()


def _count_jobs(connection: sqlite3.Connection) -> int:
    return int(connection.execute(_read_query("count_jobs.sql")).fetchone()[0])


def _count_missing(connection: sqlite3.Connection, column_name: str) -> int:
    if column_name not in PROFILE_COLUMNS:
        raise ValueError(f"Unsupported profile column: {column_name}")

    value = connection.execute(
        _read_query("count_missing_fields.sql").format(column_name=column_name)
    ).fetchone()[0]
    return int(value)


def _fetch_extreme_description(
    connection: sqlite3.Connection,
    order: str,
) -> ExtremeDescription | None:
    if order not in EXTREME_ORDERS:
        raise ValueError(f"Unsupported description ordering: {order}")

    row = connection.execute(
        _read_query("extreme_description.sql").format(order=order)
    ).fetchone()
    if row is None:
        return None

    return ExtremeDescription(
        source_id=str(row[0]),
        job_title=str(row[1]),
        description_length=int(row[2] or 0),
    )


def _build_profile(connection: sqlite3.Connection) -> DataProfile:
    total_records = _count_jobs(connection)
    average = connection.execute(_read_query("avg_description_length.sql")).fetchone()[0]

    return DataProfile(
        total_records=total_records,
        missing_job_title=_count_missing(connection, "job_title"),
        missing_company=_count_missing(connection, "company"),
        missing_description=_count_missing(connection, "description"),
        average_description_length=round(float(average)),
        shortest_description=_fetch_extreme_description(connection, "ASC"),
        longest_description=_fetch_extreme_description(connection, "DESC"),
    )


def _print_extreme(label: str, icon: str, value: ExtremeDescription | None) -> None:
    if value is None:
        print(f"{icon} {label} Description: 0 chars")
        print("   \u21b3 source_id: N/A | job_title: N/A")
        return

    print(f"{icon} {label} Description: {value.description_length} chars")
    print(f"   \u21b3 source_id: {value.source_id} | job_title: {value.job_title}")


def _print_profile(profile: DataProfile) -> None:
    print(f"--- {REPORT_ICON} DATA QUALITY REPORT ---")
    print(f"{CHART_ICON} Total Records: {profile.total_records}")
    print(
        f"{QUESTION_ICON} Missing Values -> "
        f"job_title: {profile.missing_job_title}, "
        f"company: {profile.missing_company}, "
        f"description: {profile.missing_description}"
    )
    print(
        f"{NOTE_ICON} Avg Description Length: "
        f"{profile.average_description_length} chars"
    )
    _print_extreme("Shortest", WARNING_ICON, profile.shortest_description)
    _print_extreme("Longest", ALERT_ICON, profile.longest_description)


def _has_repeated_specials(value: str | None) -> int:
    if value is None:
        return 0

    return int(REPEATED_SPECIALS.search(str(value)) is not None)


def _register_quality_functions(connection: sqlite3.Connection) -> None:
    connection.create_function(
        "HAS_REPEATED_SPECIALS",
        1,
        _has_repeated_specials,
        deterministic=True,
    )


def _label_job_quality(connection: sqlite3.Connection) -> None:
    connection.execute(_read_query("label_job_quality.sql"))


def _fetch_low_quality_jobs(connection: sqlite3.Connection) -> list[LowQualityJob]:
    rows = connection.execute(_read_query("select_low_quality_jobs.sql")).fetchall()
    return [
        LowQualityJob(
            source_id=str(row[0]),
            job_title=str(row[1]),
            company=str(row[2]),
            description_length=int(row[3] or 0),
        )
        for row in rows
    ]


def _count_low_quality_jobs(connection: sqlite3.Connection) -> int:
    return int(
        connection.execute(_read_query("count_low_quality_jobs.sql")).fetchone()[0]
    )


def _log_low_quality_jobs(low_quality_jobs: list[LowQualityJob]) -> None:
    for job in low_quality_jobs:
        logging.warning(
            (
                "%s Low-quality row: source_id=%s | job_title=%s | "
                "company=%s | description_length=%s"
            ),
            WARNING_ICON,
            job.source_id,
            job.job_title,
            job.company,
            job.description_length,
        )


def _quarantine_low_quality_jobs(connection: sqlite3.Connection) -> None:
    connection.execute(_read_query("insert_low_quality_quarantine.sql"))
    connection.execute(_read_query("delete_low_quality_jobs.sql"))


def run_data_profile(db_path) -> None:
    _configure_stdout()

    database_path = Path(db_path)
    if not database_path.exists():
        print(f"{ERROR_ICON} Database not found at {database_path}")
        return

    try:
        with sqlite3.connect(database_path) as connection:
            _ensure_profile_schema(connection)
            profile = _build_profile(connection)
            _print_profile(profile)

            _register_quality_functions(connection)
            _label_job_quality(connection)
            low_quality_count = _count_low_quality_jobs(connection)
            low_quality_jobs = _fetch_low_quality_jobs(connection)
            _log_low_quality_jobs(low_quality_jobs)
            _quarantine_low_quality_jobs(connection)
            clean_jobs_count = _count_jobs(connection)
            connection.commit()
    except sqlite3.Error as error:
        print(f"{ERROR_ICON} Unable to profile database: {error}")
        return

    print(f"{ERROR_ICON} Quarantined {low_quality_count} low-quality record(s).")
    print(f"{SUCCESS_ICON} Clean jobs remaining: {clean_jobs_count}")
