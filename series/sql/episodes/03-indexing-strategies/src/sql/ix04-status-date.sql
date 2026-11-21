-- ix04: a full-table index for q02 - all 200,000 rows, to answer a question about 1% of them.
CREATE NONCLUSTERED INDEX IX_Orders_Status_OrderDate
    ON Sales.Orders (Status, OrderDate)
    INCLUDE (CustomerId, TotalAmount);
