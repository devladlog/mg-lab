-- a16-role.sql
-- SQL Server only. The role this replica has right now (PRIMARY, SECONDARY or RESOLVING), from the local row of
-- the availability replica states. The runner's --watch polls it on both replicas to time an automatic failover.
USE master;
GO
SELECT role_desc AS Role FROM sys.dm_hadr_availability_replica_states WHERE is_local = 1;
GO
