-- d03-order-1011.sql
-- Order 1011, committed after the rogue log backup, before the next shipped log. Portable T-SQL: the local check runs it on DuckDB as well. Run it in ContosoBikesHA (the primary).
INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1011, 2, '2025-05-09', N'Placed');
INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct) VALUES
    (1011, 1, 5, 2, 39.95, 0.00);
GO
