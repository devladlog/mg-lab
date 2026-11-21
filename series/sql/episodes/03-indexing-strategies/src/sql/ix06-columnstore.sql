-- ix06: a nonclustered columnstore index for reporting.
-- Next to the rowstore table: each column stored separately and compressed, read in batch mode.
CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_Orders_Reporting
    ON Sales.Orders (OrderDate, Channel, TotalAmount);
