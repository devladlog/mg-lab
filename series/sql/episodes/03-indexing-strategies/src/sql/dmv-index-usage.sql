-- dmv-index-usage: how each index on Sales.Orders has been used since the last restart.
-- user_updates is the write cost every index adds. Counters reset when SQL Server restarts.
SELECT i.name                     AS IndexName,
       ISNULL(us.user_seeks, 0)   AS UserSeeks,
       ISNULL(us.user_scans, 0)   AS UserScans,
       ISNULL(us.user_lookups, 0) AS UserLookups,
       ISNULL(us.user_updates, 0) AS UserUpdates
FROM sys.indexes AS i
LEFT JOIN sys.dm_db_index_usage_stats AS us
  ON us.object_id = i.object_id AND us.index_id = i.index_id AND us.database_id = DB_ID()
WHERE i.object_id = OBJECT_ID(N'Sales.Orders')
ORDER BY i.index_id;
