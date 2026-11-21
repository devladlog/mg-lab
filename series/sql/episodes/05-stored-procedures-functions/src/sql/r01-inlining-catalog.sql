-- r01-inlining-catalog.sql
-- Which of our functions can SQL Server inline? is_inlineable comes from the function's definition
-- (Learn: it's 1 for every inline TVF; for a scalar UDF it depends on the constructs it uses).
SELECT o.name AS FunctionName,
       o.type_desc AS FunctionType,
       CAST(m.is_inlineable AS int) AS IsInlineable
FROM sys.sql_modules AS m
JOIN sys.objects AS o ON o.object_id = m.object_id
WHERE o.schema_id = SCHEMA_ID(N'Sales')
  AND o.type IN ('FN', 'IF', 'TF')
ORDER BY o.name;
