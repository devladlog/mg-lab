-- a07-health.sql
-- SQL Server only. Run on the PRIMARY: it reports every replica's role, mode, connection and synchronization state
-- for ContosoBikesAG (on a secondary the database view only shows the local row). SYNCHRONIZED + HEALTHY + not
-- suspended on a synchronous-commit secondary is what makes a failover lossless. Queue sizes are in KB.
-- The views need VIEW SERVER PERFORMANCE STATE on SQL Server 2022. src/ag_health.py turns the rows into verdicts.
USE master;
GO
SELECT ar.replica_server_name                  AS Replica,
       ars.role_desc                           AS Role,
       ar.availability_mode_desc               AS AvailabilityMode,
       ar.failover_mode_desc                   AS FailoverMode,
       ars.connected_state_desc                AS ConnectedState,
       drs.synchronization_state_desc          AS SyncState,
       drs.synchronization_health_desc         AS SyncHealth,
       CONVERT(int, drs.is_suspended)          AS IsSuspended,
       drs.log_send_queue_size                 AS LogSendQueueKB,
       drs.redo_queue_size                     AS RedoQueueKB
FROM sys.availability_groups AS ag
JOIN sys.availability_replicas AS ar ON ar.group_id = ag.group_id
JOIN sys.dm_hadr_availability_replica_states AS ars ON ars.replica_id = ar.replica_id AND ars.group_id = ar.group_id
LEFT JOIN sys.dm_hadr_database_replica_states AS drs
       ON drs.replica_id = ar.replica_id AND drs.group_id = ar.group_id AND drs.database_id = DB_ID(N'ContosoBikesAG')
WHERE ag.name = N'ag_contoso'
ORDER BY ar.replica_server_name;
GO
