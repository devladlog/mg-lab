-- dmv-missing-indexes: what the optimizer asked for while compiling queries in this database.
-- Kept in memory only: cleared on restart, and for a table whenever its metadata changes (creating or
-- dropping an index on it). A starting point for review, not a list of indexes to create.
SELECT TOP (10)
       mid.statement           AS TableName,
       mid.equality_columns    AS EqualityColumns,
       mid.inequality_columns  AS InequalityColumns,
       mid.included_columns    AS IncludedColumns,
       migs.user_seeks         AS UserSeeks,
       migs.avg_user_impact    AS AvgUserImpact
FROM sys.dm_db_missing_index_group_stats AS migs
JOIN sys.dm_db_missing_index_groups AS mig ON mig.index_group_handle = migs.group_handle
JOIN sys.dm_db_missing_index_details AS mid ON mid.index_handle = mig.index_handle
WHERE mid.database_id = DB_ID()
ORDER BY migs.avg_total_user_cost * migs.avg_user_impact * (migs.user_seeks + migs.user_scans) DESC;
