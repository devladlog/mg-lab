-- Hand-written examples of the kind of T-SQL you should read twice before you run it. NOT Copilot output: this
-- episode never fakes what Copilot says. tests/test_gate.py checks what the gate reports for each batch.

-- batch 1: UPDATE without WHERE (the classic)
UPDATE Sales.Orders SET Status = N'Cancelled';
GO
-- batch 2: SELECT * and a table without a schema
SELECT * FROM Orders;
GO
-- batch 3: DROP and TRUNCATE
DROP TABLE Sales.OrderLines;
TRUNCATE TABLE Sales.Orders;
GO
-- batch 4: shell access
EXEC sp_configure 'show advanced options', 1;
RECONFIGURE;
EXEC xp_cmdshell 'dir C:\';
GO
-- batch 5: dynamic SQL built from a variable
DECLARE @table sysname = N'Sales.Orders';
DECLARE @sql nvarchar(max) = N'DELETE FROM ' + @table;
EXEC (@sql);
GO
-- batch 6: permissions
GRANT SELECT ON SCHEMA::Sales TO PUBLIC;
ALTER ROLE db_owner ADD MEMBER copilot_demo_analyst;
