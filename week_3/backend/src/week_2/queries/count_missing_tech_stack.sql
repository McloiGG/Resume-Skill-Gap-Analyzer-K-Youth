SELECT COUNT(*) AS missing_count
FROM jobs
WHERE tech_stack IS NULL
   OR TRIM(tech_stack) = '';