-- h04-standby-write.sql
-- SQL Server only. Gotcha 1: the standby is readable, not writable. A write fails with error 3906 (the database is
-- read-only), and the row count does not change. The standby only moves forward by restoring log backups.
USE master;
GO
INSERT INTO ContosoBikesHA_Standby.Sales.Orders (OrderId, CustomerId, OrderDate, Status)
VALUES (9999, 1, '2025-06-01', N'Placed');
GO
SELECT N'Orders on the standby' AS Item, CONVERT(nvarchar(60), COUNT(*)) AS Result FROM ContosoBikesHA_Standby.Sales.Orders
UNION ALL
SELECT N'Order 9999 on the standby', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesHA_Standby.Sales.Orders WHERE OrderId = 9999;
GO
