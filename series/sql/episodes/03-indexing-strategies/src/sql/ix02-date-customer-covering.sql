-- ix02: covers the query, but the leading key is OrderDate:
-- the rows for one customer are spread over the whole index.
-- Same columns as ix03, wrong order: SQL Server can only scan it.
CREATE NONCLUSTERED INDEX IX_Orders_OrderDate_CustomerId
    ON Sales.Orders (OrderDate DESC, CustomerId)
    INCLUDE (TotalAmount);
