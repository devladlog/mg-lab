-- r02-reader-login.sql
-- SQL Server only. The account the report server uses to read the data: a SQL login with EXECUTE on schema Rpt only.
-- The password is never in this file: the runner reads it from the environment variable RS_READER_PASSWORD and
-- sends it as the value of the variable @pwd (sqlcmd users: -v is not needed, edit the DECLARE line by hand).
-- Run against master first batch, ContosoBikesRpt second batch (the runner does both).
USE master;
GO
DECLARE @pwd nvarchar(128) = N'<set-RS_READER_PASSWORD>';
DECLARE @sql nvarchar(max);
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'rs_reader')
BEGIN
    SET @sql = N'CREATE LOGIN rs_reader WITH PASSWORD = ' + QUOTENAME(@pwd, '''') + N', CHECK_POLICY = ON, DEFAULT_DATABASE = ContosoBikesRpt;';
    EXEC (@sql);
END
GO
USE ContosoBikesRpt;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'rs_reader')
    CREATE USER rs_reader FOR LOGIN rs_reader;
GO
GRANT EXECUTE ON SCHEMA::Rpt TO rs_reader;
GO
