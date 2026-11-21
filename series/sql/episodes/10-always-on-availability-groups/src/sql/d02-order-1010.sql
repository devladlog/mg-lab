-- d02-order-1010.sql
-- Order 1010: written on the NEW primary after the planned failover. Portable T-SQL: the local check runs it on DuckDB as well. Run it in ContosoBikesAG on the current primary.
INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1010, 3, '2025-05-06', N'Placed');
INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct) VALUES
    (1010, 1, 3, 2, 24.50, 0.00);
GO
