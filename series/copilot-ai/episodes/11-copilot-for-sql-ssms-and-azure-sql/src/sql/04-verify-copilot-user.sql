-- 04-verify-copilot-user.sql
-- Run in ContosoCopilot CONNECTED AS copilot_demo_analyst (not as an administrator). It proves what Copilot can do once
-- the constitution makes SSMS run its queries as GHCP_DB_User. The write attempt is wrapped so nothing can change.
-- This is an administrator script (EXECUTE AS): tsql_gate correctly BLOCKs it in read-only mode.
USE ContosoCopilot;
GO
SELECT SUSER_SNAME() AS connected_as, USER_NAME() AS database_user;
GO
EXECUTE AS USER = N'GHCP_DB_User';
    SELECT USER_NAME() AS running_as;
    SELECT COUNT(*) AS visible_orders FROM Sales.Orders;
    SELECT permission_name FROM sys.fn_my_permissions(N'Sales.Orders', N'OBJECT') ORDER BY permission_name;
    BEGIN TRY
        UPDATE Sales.Orders SET Status = N'Cancelled' WHERE OrderId = 1;
        SELECT N'UNEXPECTED: the update ran' AS result;
    END TRY
    BEGIN CATCH
        SELECT ERROR_NUMBER() AS error_number, ERROR_MESSAGE() AS error_message;   -- 229: permission denied
    END CATCH;
REVERT;
GO
-- The same statement as the analyst himself would be allowed (he is in db_datawriter), so the ROLLBACK matters:
BEGIN TRANSACTION;
    UPDATE Sales.Orders SET Status = N'Cancelled' WHERE OrderId = 1;
    SELECT @@ROWCOUNT AS rows_changed_as_analyst;
ROLLBACK TRANSACTION;
GO
