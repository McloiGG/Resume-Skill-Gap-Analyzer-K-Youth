SELECT COALESCE(
    SUM(
        CASE
            WHEN {column_name} IS NULL OR TRIM({column_name}) = ''
            THEN 1
            ELSE 0
        END
    ),
    0
)
FROM jobs
