-- Run in the portal's Query editor (signed in with Microsoft Entra ID) after infra/smoke.sh.

-- 1. Who am I? With Entra-only authentication there is no SQL login to fall back to.
SELECT SUSER_SNAME() AS signed_in_as, DB_NAME() AS database_name,
       DATABASEPROPERTYEX(DB_NAME(), 'ServiceObjective') AS service_objective;

-- 2. The orders the smoke test wrote, newest first (the same order the keyset index serves)
SELECT TOP (10) o.Id, o.CustomerId, o.CreatedUtc, o.Status, o.Total, COUNT(l.Id) AS lines
FROM dbo.Orders AS o JOIN dbo.OrderLines AS l ON l.OrderId = o.Id
GROUP BY o.Id, o.CustomerId, o.CreatedUtc, o.Status, o.Total
ORDER BY o.CreatedUtc DESC, o.Id DESC;

-- 3. One row per Idempotency-Key, enforced by the unique index (this returns nothing)
SELECT IdempotencyKey, COUNT(*) AS n FROM dbo.Orders GROUP BY IdempotencyKey HAVING COUNT(*) > 1;

-- 4. Sessions that keep the free-tier database from auto-pausing (from Microsoft Learn's
--    auto-pause troubleshooting). Close the query editor afterwards: it is one of them.
SELECT session_id, host_name, program_name, client_interface_name, login_name, status, login_time, last_request_start_time
FROM sys.dm_exec_sessions
WHERE database_id = DB_ID() AND is_user_process = 1;
