UPDATE jobs
SET
    job_title = ?,
    company = ?,
    description = ?,
    tech_stack = ?,
    content_hash = ?,
    quality = ''
WHERE source_id = ?
