UPDATE jobs
SET quality = CASE
    WHEN description IS NULL OR LENGTH(description) < 100 THEN 'LOW'
    WHEN job_title IS NULL OR TRIM(job_title) = '' THEN 'LOW'
    WHEN company IS NULL OR TRIM(company) = '' THEN 'LOW'
    WHEN description IS NULL OR TRIM(description) = '' THEN 'LOW'
    WHEN HAS_REPEATED_SPECIALS(
        COALESCE(job_title, '') || ' ' ||
        COALESCE(company, '') || ' ' ||
        COALESCE(description, '')
    ) = 1 THEN 'LOW'
    ELSE 'HIGH'
END
