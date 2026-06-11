SELECT source_id, job_title, company, LENGTH(description) AS description_length
FROM jobs
WHERE quality = 'LOW'
ORDER BY source_id ASC
