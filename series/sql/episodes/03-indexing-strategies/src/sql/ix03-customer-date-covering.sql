-- ix03: equality column first, then the ORDER BY column.
-- One seek to customer 4242, rows already in OrderDate DESC order.
-- No lookup (TotalAmount is INCLUDEd), no sort. OrderId, the clustered key, is in every index anyway.
CREATE NONCLUSTERED INDEX IX_Orders_CustomerId_OrderDate
    ON Sales.Orders (CustomerId, OrderDate DESC)
    INCLUDE (TotalAmount);
