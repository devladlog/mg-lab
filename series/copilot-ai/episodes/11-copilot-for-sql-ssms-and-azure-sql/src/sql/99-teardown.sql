-- 99-teardown.sql
-- SQL Server only. Run against master as the lab Administrator after the recording.
IF DB_ID(N'ContosoCopilot') IS NOT NULL
BEGIN
    ALTER DATABASE ContosoCopilot SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE ContosoCopilot;
END
GO
IF SUSER_ID(N'copilot_demo_analyst') IS NOT NULL
    DROP LOGIN copilot_demo_analyst;
GO
