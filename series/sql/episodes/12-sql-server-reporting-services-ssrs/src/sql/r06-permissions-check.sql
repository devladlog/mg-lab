-- r06-permissions-check.sql
-- SQL Server only. What the report server's account (rs_reader) may do: run the two report procedures, and nothing
-- on the order tables. Evaluated as rs_reader with EXECUTE AS, so it needs no second connection.
USE ContosoBikesRpt;
GO
EXECUTE AS USER = N'rs_reader';
SELECT N'EXECUTE on Rpt.usp_SalesByProduct' AS Probe, CONVERT(int, HAS_PERMS_BY_NAME(N'Rpt.usp_SalesByProduct', N'OBJECT', N'EXECUTE')) AS Allowed
UNION ALL SELECT N'EXECUTE on Rpt.usp_Regions', CONVERT(int, HAS_PERMS_BY_NAME(N'Rpt.usp_Regions', N'OBJECT', N'EXECUTE'))
UNION ALL SELECT N'SELECT on Sales.Orders', CONVERT(int, HAS_PERMS_BY_NAME(N'Sales.Orders', N'OBJECT', N'SELECT'))
UNION ALL SELECT N'SELECT on Sales.Customers', CONVERT(int, HAS_PERMS_BY_NAME(N'Sales.Customers', N'OBJECT', N'SELECT'));
REVERT;
GO
