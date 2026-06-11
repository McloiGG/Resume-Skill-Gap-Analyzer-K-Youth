# Week 1: Data Component

## Project Description

This project implements the Week 1 data pipeline for a resume skill gap analyzer. The pipeline collects saved Jobstreet job postings, extracts the HTML content, converts each posting into structured JSON, loads clean records into SQLite, and runs a basic data quality profile.

The pipeline follows a folder-based Medallion Architecture:

- `data/0_source/`: raw `.mhtml` source files
- `data/1_bronze/`: extracted raw HTML files
- `data/2_silver/`: structured JSON records
- `data/3_gold/`: SQLite database output

The Gold layer also includes bonus data engineering features: structured logging, SQL query files, content hashing for idempotent updates, quality labels, and a quarantine table for low-quality records.

## Setup Instructions

### Prerequisites

- Python `3.14`
- `uv` for dependency and virtual environment management
- Git

No API keys or environment variables are required for Week 1.

### Install Dependencies

From this `week_1` directory:

```powershell
uv sync
```

This installs the dependencies declared in `pyproject.toml`, including:

- `beautifulsoup4`/`bs4` for HTML parsing
- `pydantic` for validating extracted job records
- `ruff` for lint checks

If `uv` is not installed, install it first from the official Astral documentation, then rerun `uv sync`.

## Usage

Run commands from this `week_1` directory.

```powershell
uv run python main.py ingest
uv run python main.py process
uv run python main.py load
uv run python main.py profile
```

To run the full pipeline in order:

```powershell
uv run python main.py all
```

Available commands:

- `ingest`: extract `.mhtml` files from `data/0_source/` into HTML files in `data/1_bronze/`
- `process`: parse Bronze HTML files into validated JSON records in `data/2_silver/`
- `load`: load Silver JSON records into `data/3_gold/jobs.db`
- `profile`: print a data quality report, label records as `HIGH` or `LOW`, and move `LOW` records into `jobs_quarantine`
- `all`: run `ingest`, `process`, `load`, and `profile` in sequence

Expected output includes stage summaries, a Gold load summary, a data quality report, and a concise quarantine summary. Detailed per-file messages are written with Python `logging`.

Example Gold summary:

```text
Total: 84 | Inserted: 84 | Updated: 0 | Skipped: 0
```

Example quality result after profiling:

```text
Quarantined 1 low-quality record(s).
Clean jobs remaining: 83
```

## Validation

Compile the Python files:

```powershell
uv run python -m py_compile main.py src/ingestor.py src/processor.py src/loader.py src/profiler.py
```

Run Ruff:

```powershell
uv run ruff check main.py src
```

Inspect the SQLite output:

```powershell
uv run python -c "import sqlite3; con=sqlite3.connect('data/3_gold/jobs.db'); print([r[1] for r in con.execute('PRAGMA table_info(jobs)')]); print([r[1] for r in con.execute('PRAGMA table_info(jobs_quarantine)')]); print(con.execute('SELECT quality, COUNT(*) FROM jobs GROUP BY quality').fetchall()); print(con.execute('SELECT quality, COUNT(*) FROM jobs_quarantine GROUP BY quality').fetchall())"
```

Expected tables:

- `jobs`: clean Gold records with `quality = 'HIGH'`
- `jobs_quarantine`: low-quality records with `quality = 'LOW'`

## Technical Reflections

### Day 1: The Extractor (Medallion & Lakehouses)

Keeping the original raw HTML files makes the pipeline easier to audit, debug, and recover. If the parser extracts the wrong title or misses a company name, the raw source can be inspected again without recollecting data from Jobstreet.

This mirrors how data lakes work in industry. Raw data is preserved first, then transformed into cleaner layers later. That separation protects the pipeline from losing source evidence when transformation logic changes or fails.

### Day 2: Treatment Plant (ETL vs ELT & Scale)

Cloud systems often prefer ELT because storage is cheap and compute can be applied later with different transformation rules. Loading raw data first also means teams can reprocess history when schemas, business rules, or quality checks change.

Sequential file processing is simple but slow and fragile at larger scale. If one machine processes one file at a time, throughput is limited and failures require manual recovery. Distributed systems such as Spark split work across many workers, making large transformations faster and more resilient.

### Day 3: The Blueprint & The Vault (Storage & Contracts)

If an important field like `job_title` disappears, the pipeline should fail or skip the bad record early instead of silently inserting incomplete data. A missing title can break analytics, dashboards, matching logic, and downstream skill extraction.

Data contracts make expectations explicit before data reaches the warehouse layer. Idempotent loading also prevents duplicate records: the original version used `INSERT OR IGNORE`, while the current version uses `source_id` plus `content_hash` to skip unchanged records and update changed records.

### Day 4: The QA Inspector & Orchestrator (Orchestration & DAGs)

If `processor.py` crashes halfway, some files may already be written while others are missing. Without orchestration, a user has to inspect the folder state and manually rerun the correct stage.

Production orchestrators such as Airflow model pipelines as DAGs with dependencies, retries, logs, and scheduling. That makes recovery more reliable because each stage can be retried, monitored, and audited without guessing what ran successfully.
