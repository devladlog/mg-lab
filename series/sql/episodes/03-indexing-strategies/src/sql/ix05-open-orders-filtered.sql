-- ix05: a filtered index - only the Open orders.
-- The query's predicate (Status = 'Open') matches the filter, so Status doesn't need to be in the index.
CREATE NONCLUSTERED INDEX IX_Orders_Open
    ON Sales.Orders (OrderDate)
    INCLUDE (CustomerId, TotalAmount)
    WHERE Status = 'Open';
