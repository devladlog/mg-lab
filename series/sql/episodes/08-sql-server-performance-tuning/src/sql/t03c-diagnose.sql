-- t03c-diagnose.sql
-- SQL Server only. Window 3: who is waiting, for what, and who is holding it? blocking_session_id (non-zero: the request
-- is blocked), wait_type and wait_time (ms of the current wait), the blocked statement, and the last statement of the
-- blocker's connection. open_transaction_count of the blocker's SESSION says whether it sits in an open transaction.
SELECT r.session_id AS BlockedSession,
       r.blocking_session_id AS BlockerSession,
       r.wait_type AS WaitType,
       r.wait_time AS WaitMs,
       r.wait_resource AS WaitResource,
       bs.open_transaction_count AS BlockerOpenTransactions,
       t.text AS BlockedStatement,
       bt.text AS BlockerLastStatement
FROM sys.dm_exec_requests AS r
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) AS t
LEFT JOIN sys.dm_exec_sessions AS bs ON bs.session_id = r.blocking_session_id
LEFT JOIN sys.dm_exec_connections AS bc ON bc.session_id = r.blocking_session_id
OUTER APPLY sys.dm_exec_sql_text(bc.most_recent_sql_handle) AS bt
WHERE r.blocking_session_id <> 0
  AND t.text LIKE N'%mglab-blocked-report%'
  AND t.text NOT LIKE N'%dm_exec_requests%';
