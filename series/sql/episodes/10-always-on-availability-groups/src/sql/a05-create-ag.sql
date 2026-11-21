-- a05-create-ag.sql
-- SQL Server only. Run on the primary (CON-SQL01). One availability group, one database, two replicas:
-- * SYNCHRONOUS_COMMIT + FAILOVER_MODE = AUTOMATIC: no data loss, and automatic failover when the secondary is
--   synchronized (Learn: automatic failover needs synchronous commit and a synchronized secondary);
-- * SEEDING_MODE = AUTOMATIC: SQL Server streams the database to the secondary (the secondary must be granted
--   CREATE ANY DATABASE after it joins: a06). No manual backup/restore of the database;
-- * SECONDARY_ROLE (ALLOW_CONNECTIONS = NO) is the default, written out: the gotcha of a08 depends on it;
-- * DB_FAILOVER = ON: a database that is no longer ONLINE also triggers failover;
-- * CLUSTER_TYPE = WSFC: Windows Server Failover Cluster (None is not supported as high availability).
-- Replica names are the Windows computer names, as Learn requires. lab.contoso.com is the lab's AD domain.
USE master;
GO
CREATE AVAILABILITY GROUP ag_contoso
WITH (CLUSTER_TYPE = WSFC, DB_FAILOVER = ON)
FOR DATABASE ContosoBikesAG
REPLICA ON
    'CON-SQL01' WITH (ENDPOINT_URL = 'TCP://CON-SQL01.lab.contoso.com:5022',
                      AVAILABILITY_MODE = SYNCHRONOUS_COMMIT, FAILOVER_MODE = AUTOMATIC,
                      SEEDING_MODE = AUTOMATIC, SECONDARY_ROLE (ALLOW_CONNECTIONS = NO)),
    'CON-SQL02' WITH (ENDPOINT_URL = 'TCP://CON-SQL02.lab.contoso.com:5022',
                      AVAILABILITY_MODE = SYNCHRONOUS_COMMIT, FAILOVER_MODE = AUTOMATIC,
                      SEEDING_MODE = AUTOMATIC, SECONDARY_ROLE (ALLOW_CONNECTIONS = NO));
GO
