-- a02-prereqs.sql
-- SQL Server only. Run on each replica. The prerequisites the AG needs, read from the instance itself:
-- Always On enabled (IsHadrEnabled = 1; the instance needs a restart after enabling it), the same collation and
-- version on both replicas (Learn: same SQL Server version and collation), and the WSFC this instance belongs to:
-- quorum state and the cluster nodes that are UP (the file share witness is a member too, so only nodes are counted).
-- The views need VIEW SERVER PERFORMANCE STATE on SQL Server 2022.
USE master;
GO
SELECT CONVERT(nvarchar(60), SERVERPROPERTY(N'ServerName'))                  AS Node,
       CONVERT(int, SERVERPROPERTY(N'IsHadrEnabled'))                         AS HadrEnabled,
       CONVERT(nvarchar(128), SERVERPROPERTY(N'Collation'))                   AS Collation,
       CONVERT(nvarchar(32), SERVERPROPERTY(N'ProductVersion'))               AS ProductVersion,
       (SELECT TOP (1) quorum_state_desc FROM sys.dm_hadr_cluster)            AS QuorumState,
       (SELECT COUNT(*) FROM sys.dm_hadr_cluster_members
        WHERE member_type_desc = N'CLUSTER_NODE' AND member_state_desc = N'UP') AS NodesUp;
GO
