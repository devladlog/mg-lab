-- ix01: the obvious first index - the column in the WHERE clause.
-- Finds the 7 rows directly, but every other column still comes from the clustered index (Key Lookup).
CREATE NONCLUSTERED INDEX IX_Orders_CustomerId
    ON Sales.Orders (CustomerId);
