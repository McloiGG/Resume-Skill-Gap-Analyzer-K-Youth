CREATE TABLE IF NOT EXISTS jobs_quarantine (
    source_id TEXT PRIMARY KEY,
    job_title TEXT,
    company TEXT,
    description TEXT,
    tech_stack TEXT,
    content_hash TEXT NOT NULL DEFAULT '',
    quality TEXT NOT NULL DEFAULT ''
)
