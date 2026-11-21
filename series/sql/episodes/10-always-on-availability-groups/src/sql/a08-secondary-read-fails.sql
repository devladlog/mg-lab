-- a08-secondary-read-fails.sql
-- SQL Server only. Run on the SECONDARY (CON-SQL02). Gotcha: the replica was created with ALLOW_CONNECTIONS = NO, so
-- its copy of the database is not readable. Error 976: "The target database, 'ContosoBikesAG', is participating in an
-- availability group and is currently not accessible for queries. Either data movement is suspended or the
-- availability replica isn't enabled for read access." Nothing is wrong with the group; this is the setting.
USE master;
GO
SELECT COUNT(*) AS Orders FROM ContosoBikesAG.Sales.Orders;
GO
