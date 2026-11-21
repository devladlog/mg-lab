-- d04-order-1012.sql
-- Order 1012, committed after the last shipped log: only the tail-log backup holds it. Portable T-SQL: the local check runs it on DuckDB as well. Run it in ContosoBikesHA (the primary).
INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1012, 4, '2025-05-10', N'Placed');
INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct) VALUES
    (1012, 1, 3, 1, 24.50, 0.00);
GO
