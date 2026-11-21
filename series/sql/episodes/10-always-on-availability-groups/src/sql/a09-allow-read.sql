-- a09-allow-read.sql
-- SQL Server only. Run on the primary. The fix for a08: make the secondary role readable on both replicas (both,
-- because after a failover the other replica becomes the secondary). ALL allows any read-only connection; READ_ONLY
-- would require ApplicationIntent=ReadOnly in the connection string. No restart, no re-seeding.
USE master;
GO
ALTER AVAILABILITY GROUP ag_contoso MODIFY REPLICA ON 'CON-SQL01' WITH (SECONDARY_ROLE (ALLOW_CONNECTIONS = ALL));
GO
ALTER AVAILABILITY GROUP ag_contoso MODIFY REPLICA ON 'CON-SQL02' WITH (SECONDARY_ROLE (ALLOW_CONNECTIONS = ALL));
GO
