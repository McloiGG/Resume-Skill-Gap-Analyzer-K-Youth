SELECT source_id, job_title, company, description
FROM jobs
WHERE tech_stack IS NULL
   OR TRIM(tech_stack) = ''
ORDER BY rowid
LIMIT :limit;