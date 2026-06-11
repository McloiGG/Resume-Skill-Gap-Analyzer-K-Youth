# K-Youth Resume Skill Gap Analyzer

## Project Description

This repository contains the three-week Resume Skill Gap Analyzer project for
K-Youth. Week 1 builds the local data engineering component: an ETL pipeline
that extracts saved job postings from `.mhtml` files, cleans the HTML into
structured JSON, loads clean records into SQLite, and profiles the final data.

Week 1 follows a simplified Medallion Architecture:

- `week_1/data/0_source/`: raw `.mhtml` source files
- `week_1/data/1_bronze/`: extracted HTML files
- `week_1/data/2_silver/`: validated JSON records
- `week_1/data/3_gold/`: final SQLite database, `jobs.db`

The final Gold table uses `source_id`, `job_title`, `company`, `description`,
and `tech_stack`, with bonus columns for `content_hash` and `quality`.

## Setup Instructions

Prerequisites:

- Python `3.14`
- `uv`
- Git

From the Week 1 directory, install dependencies:

```powershell
cd week_1
uv sync
```

No API keys or environment variables are required for Week 1.

## Usage

Run commands from `week_1`:

```powershell
uv run python main.py ingest
uv run python main.py process
uv run python main.py load
uv run python main.py profile
uv run python main.py all
```

Command summary:

- `ingest`: extract `.mhtml` files from `data/0_source/` into `data/1_bronze/`
- `process`: parse Bronze HTML into validated JSON in `data/2_silver/`
- `load`: load Silver JSON into `data/3_gold/jobs.db`
- `profile`: print quality metrics and move low-quality rows to quarantine
- `all`: run `ingest`, `process`, `load`, and `profile` in order

More detailed Week 1 documentation is in `week_1/README.md`.

## Technical Reflections

### Day 1: The Extractor (Medallion and Lakehouses)

Keeping raw HTML makes the pipeline easier to audit and recover. If parsing
logic changes or a field is extracted incorrectly, the original source is still
available and the Bronze-to-Silver transformation can be rerun without
recollecting data.

### Day 2: Treatment Plant (ETL vs ELT and Scale)

Cloud systems often prefer ELT because raw data can be stored cheaply and
transformed later with scalable compute. Sequential local file processing is
simple, but it becomes slow and fragile as volume grows. Distributed systems
split the work across many workers for better throughput and recovery.

### Day 3: The Blueprint and The Vault (Storage and Contracts)

If a critical field such as `job_title` disappears, the pipeline should reject
or skip the bad record before it reaches the database. Failing early prevents
silent nulls from breaking dashboards, analytics, or downstream skill matching.
Idempotent loading prevents repeated runs from creating duplicate records.

### Day 4: The QA Inspector and Orchestrator (Orchestration and DAGs)

If `processor.py` crashes halfway, some Silver files may exist while others are
missing. Manual reruns require a human to inspect the partial state. Production
orchestrators such as Airflow track dependencies, retries, schedules, and logs
so failed stages can be retried more reliably.
