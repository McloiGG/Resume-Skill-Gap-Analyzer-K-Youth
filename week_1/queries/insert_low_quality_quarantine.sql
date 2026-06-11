INSERT OR REPLACE INTO jobs_quarantine (
    source_id,
    job_title,
    company,
    description,
    tech_stack,
    content_hash,
    quality
)
SELECT
    source_id,
    job_title,
    company,
    description,
    tech_stack,
    content_hash,
    quality
FROM jobs
WHERE quality = 'LOW'
