SELECT source_id, tech_stack
FROM jobs
WHERE tech_stack IS NOT NULL
  AND TRIM(tech_stack) != ''
ORDER BY rowid;