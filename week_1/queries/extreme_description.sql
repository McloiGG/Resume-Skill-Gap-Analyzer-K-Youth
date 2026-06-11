SELECT source_id, job_title, LENGTH(description) AS description_length
FROM jobs
ORDER BY description_length {order}, source_id ASC
LIMIT 1
