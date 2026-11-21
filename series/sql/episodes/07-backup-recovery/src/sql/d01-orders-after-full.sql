-- d01-orders-after-full.sql
-- Two orders taken after the full backup (so the differential has something to hold).
-- Portable T-SQL: the local check runs it on DuckDB as well.
INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1009, 1, '2025-05-05', N'Placed'),
    (1010, 3, '2025-05-06', N'Placed');
INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct) VALUES
    (1009, 1, 1, 1, 89.90, 0.00),
    (1010, 1, 3, 2, 24.50, 0.00);
GO
