-- a10-secondary-read.sql
-- SQL Server only. Run on a SECONDARY: the order count it can see and the role this replica has right now.
-- A synchronous commit hardens the log on the secondary before the primary commits, but REDO (applying the log to
-- the data pages) is asynchronous: a read on the secondary can briefly lag behind a commit on the primary. Learn:
-- a change isn't visible on the secondary until it's applied there, usually within seconds. The runner polls this query.
USE master;
GO
SELECT N'Orders on this replica' AS Item, CONVERT(nvarchar(60), COUNT(*)) AS Result FROM ContosoBikesAG.Sales.Orders
UNION ALL
SELECT N'Role of this replica', CONVERT(nvarchar(60), role_desc)
FROM sys.dm_hadr_availability_replica_states WHERE is_local = 1;
GO
