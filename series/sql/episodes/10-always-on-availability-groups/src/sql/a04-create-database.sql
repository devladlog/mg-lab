-- a04-create-database.sql
-- SQL Server only. Run on the primary (CON-SQL01), in master. The throwaway database of this episode: FULL recovery,
-- which an availability group database requires (Learn: user database, read-write, multi-user, FULL recovery, at least
-- one full backup). The tables and data are episode 5's (01-schema-and-data.sql, run next in this database).
USE master;
GO
IF DB_ID(N'ContosoBikesAG') IS NULL
    CREATE DATABASE ContosoBikesAG;
GO
ALTER DATABASE ContosoBikesAG SET RECOVERY FULL;
GO
