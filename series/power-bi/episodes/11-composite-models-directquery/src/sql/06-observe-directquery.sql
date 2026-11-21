-- Which statements did Power BI send to SQL Server? Run in SSMS (or sqlcmd) right after a DAX query or a visual refreshed.
-- Power BI connects with the database as initial catalog, so its statements show up with the table names in the text.
-- A query that an aggregation answered leaves nothing here: execution_count and last_execution_time don't move.
USE [ContosoBikesDW];
GO
SELECT TOP (20)
       qs.last_execution_time,
       qs.execution_count,
       qs.last_rows                          AS last_row_count,
       qs.last_elapsed_time / 1000           AS last_ms,
       LEFT(REPLACE(REPLACE(st.text, CHAR(13), N' '), CHAR(10), N' '), 600) AS statement_start
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
WHERE (st.text LIKE N'%FactSales%' OR st.text LIKE N'%vwSalesAgg%' OR st.text LIKE N'%DimCustomer%')
  AND st.text NOT LIKE N'%dm_exec_query_stats%'
ORDER BY qs.last_execution_time DESC;
GO
