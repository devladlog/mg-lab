-- 02-copilot-user.sql
-- Run in ContosoCopilot after 01-contoso-copilot.sql, as the lab Administrator.
-- Follows Learn "Execution context for GitHub Copilot in SQL Server Management Studio": a dedicated database user that
-- is not mapped to a login, with only the permissions Copilot needs, plus IMPERSONATE for the people who may use it.
-- SQL Server enforces these permissions; Copilot's approval prompts and read-only classifier do not replace them.
USE ContosoCopilot;
GO
IF USER_ID(N'GHCP_DB_User') IS NULL
    CREATE USER GHCP_DB_User WITHOUT LOGIN;
GO
GRANT SELECT ON SCHEMA::Sales     TO GHCP_DB_User;
GRANT SELECT ON SCHEMA::Reporting TO GHCP_DB_User;
-- No INSERT, UPDATE, DELETE, EXECUTE or DDL permissions on purpose. Add them one by one, only if a use case needs them.
GO
-- The person who works in SSMS: an ordinary developer login with read and write access to the demo database.
IF USER_ID(N'copilot_demo_analyst') IS NULL
    CREATE USER copilot_demo_analyst FOR LOGIN copilot_demo_analyst;
GO
ALTER ROLE db_datareader ADD MEMBER copilot_demo_analyst;
ALTER ROLE db_datawriter ADD MEMBER copilot_demo_analyst;
GO
-- Learn: without IMPERSONATE on the Copilot user, Copilot does not work for that person (by design, no silent fallback).
GRANT IMPERSONATE ON USER::GHCP_DB_User TO copilot_demo_analyst;
GO
