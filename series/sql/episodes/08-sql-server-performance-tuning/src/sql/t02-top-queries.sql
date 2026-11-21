-- t02-top-queries.sql
-- SQL Server only. Which statements cost the most? sys.dm_exec_query_stats has one row per statement in the plan cache:
-- executions and cumulative logical reads, from the moment the plan was cached. The offsets cut the statement out of the
-- batch text (the standard idiom: they are in bytes, so they are halved for nvarchar). The lab filters on its own
-- markers; on a real server you drop the filter and sort by total_logical_reads, total_worker_time or total_elapsed_time.
-- Query Store (episode 4) keeps the same numbers across restarts and plan evictions; this DMV does not.
SELECT CASE WHEN s.StatementText LIKE N'%mglab-w-scan%' THEN N'scan' ELSE N'seek' END AS Workload,
       qs.execution_count AS Executions,
       ROW_NUMBER() OVER (ORDER BY qs.total_logical_reads DESC) AS RankByReads,
       qs.total_logical_reads / qs.execution_count AS AvgLogicalReads
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
CROSS APPLY (SELECT SUBSTRING(st.text, qs.statement_start_offset / 2 + 1,
                              (CASE WHEN qs.statement_end_offset = -1 THEN DATALENGTH(st.text) ELSE qs.statement_end_offset END
                               - qs.statement_start_offset) / 2 + 1) AS StatementText) AS s
WHERE s.StatementText LIKE N'SELECT @%mglab-w-%'
ORDER BY RankByReads;
