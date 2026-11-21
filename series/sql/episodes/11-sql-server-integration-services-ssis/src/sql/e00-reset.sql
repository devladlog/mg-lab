-- e00-reset.sql
-- SQL Server only. Run against master on CON-SQL01. Drops episode 11's throwaway database (safe to re-run).
-- The SSIS catalog side (folder, project, environment) is removed by c99-catalog-cleanup.sql.
USE master;
GO
IF DB_ID(N'ContosoBikesEtl') IS NOT NULL
BEGIN
    ALTER DATABASE ContosoBikesEtl SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE ContosoBikesEtl;
END
GO
