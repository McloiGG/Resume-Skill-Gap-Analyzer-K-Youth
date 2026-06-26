SELECT source_id, job_title, company, description
FROM jobs
ORDER BY rowid
LIMIT :limit;