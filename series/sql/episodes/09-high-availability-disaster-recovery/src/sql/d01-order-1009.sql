-- d01-order-1009.sql
-- Order 1009, committed before the first log backup is shipped. Portable T-SQL: the local check runs it on DuckDB as well. Run it in ContosoBikesHA (the primary).
INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1009, 1, '2025-05-05', N'Placed');
INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct) VALUES
    (1009, 1, 1, 1, 89.90, 0.00);
GO
