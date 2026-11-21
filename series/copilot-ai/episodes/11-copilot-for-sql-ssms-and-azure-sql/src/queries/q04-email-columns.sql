-- q04: "What columns store email addresses?" (a prompt from Learn's scenario list, answered from the catalog)
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE COLUMN_NAME LIKE N'%mail%'
ORDER BY TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME;
