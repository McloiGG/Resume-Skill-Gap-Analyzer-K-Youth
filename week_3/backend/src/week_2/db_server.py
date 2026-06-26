from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "jobs_d1.db"

mcp = FastMCP("SQLite-Service")


def _db_path() -> Path:
    return Path(os.environ.get("TAG_DATA_DB_PATH", str(DEFAULT_DB_PATH))).resolve()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_db_path())
    connection.row_factory = sqlite3.Row
    return connection


@mcp.tool
def query_db(
    sql_query: str,
    parameters: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute a parameterized SQL script against the configured SQLite database."""
    with _connect() as connection:
        if isinstance(parameters, list):
            cursor = connection.executemany(sql_query, parameters)
        else:
            cursor = connection.execute(sql_query, parameters or {})

        if cursor.description:
            return {
                "rows": [dict(row) for row in cursor.fetchall()],
                "rowcount": cursor.rowcount,
            }

        connection.commit()
        return {"rows": [], "rowcount": cursor.rowcount}


if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="WARNING")