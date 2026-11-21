-- a12-failover.sql
-- SQL Server only. A planned manual failover: run it on the replica that should BECOME the primary (the target
-- secondary). It needs synchronous commit and a synchronized secondary, so it loses no data. The statement returns
-- when the target accepts it; recovery of the database continues in the background, which is why the runner polls.
-- Do not use Failover Cluster Manager to fail over an availability group (Learn).
USE master;
GO
ALTER AVAILABILITY GROUP ag_contoso FAILOVER;
GO
