-- h09-write-on-promoted.sql
-- A write on the promoted copy: it is a normal database now. Plain, portable T-SQL: the local check runs the INSERTs too.
INSERT INTO ContosoBikesHA_Standby.Sales.Orders (OrderId, CustomerId, OrderDate, Status)
VALUES (1013, 2, '2025-05-11', N'Placed');
INSERT INTO ContosoBikesHA_Standby.Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct)
VALUES (1013, 1, 2, 1, 649.00, 0.00);
GO
SELECT N'Orders on the promoted copy' AS Item, CONVERT(nvarchar(60), COUNT(*)) AS Result FROM ContosoBikesHA_Standby.Sales.Orders
UNION ALL
SELECT N'Order 1013 on the promoted copy', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesHA_Standby.Sales.Orders WHERE OrderId = 1013;
GO
