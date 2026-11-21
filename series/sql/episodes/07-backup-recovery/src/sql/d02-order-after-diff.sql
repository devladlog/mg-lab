-- d02-order-after-diff.sql
-- One more order, after the differential: it is only in the transaction log.
INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1011, 2, '2025-05-12', N'Placed');
INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct) VALUES
    (1011, 1, 5, 2, 39.95, 0.00);
GO
