-- 02-indexes.sql
-- The starting point for episode 4: ordinary, sensible indexes. Every problem in this episode happens
-- WITH the right index in place - the query or the plan cache keeps SQL Server from using it well.
-- Re-runnable. Also removes the indexes episode 3 may have left on Sales.Orders.
DROP INDEX IF EXISTS IX_Orders_CustomerId_OrderDate ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_OrderDate_CustomerId ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_Status_OrderDate ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_Open ON Sales.Orders;
DROP INDEX IF EXISTS NCCI_Orders_Reporting ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_CustomerId ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_OrderDate ON Sales.Orders;
DROP INDEX IF EXISTS UX_Customers_AccountNumber ON Sales.Customers;
GO
-- the foreign key column, narrow on purpose: other columns come from the clustered index (Key Lookup)
CREATE NONCLUSTERED INDEX IX_Orders_CustomerId ON Sales.Orders (CustomerId);
-- date range reports
CREATE NONCLUSTERED INDEX IX_Orders_OrderDate ON Sales.Orders (OrderDate) INCLUDE (TotalAmount);
-- account numbers are digits stored as text: varchar(12)
CREATE UNIQUE NONCLUSTERED INDEX UX_Customers_AccountNumber ON Sales.Customers (AccountNumber);
GO
