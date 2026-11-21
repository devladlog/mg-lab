-- a06-join-ag.sql
-- SQL Server only. Run on the secondary (CON-SQL02) right after a05. JOIN attaches this replica to the group;
-- GRANT CREATE ANY DATABASE lets the group create the seeded database here (automatic seeding). Progress is visible
-- in sys.dm_hadr_automatic_seeding; the health query (a07) shows the result.
USE master;
GO
ALTER AVAILABILITY GROUP ag_contoso JOIN;
GO
ALTER AVAILABILITY GROUP ag_contoso GRANT CREATE ANY DATABASE;
GO
