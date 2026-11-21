-- ix00: back to the starting point - only the clustered primary key on Sales.Orders.
-- The runner executes this before every step, so each step's plan depends only on that step's index.
DROP INDEX IF EXISTS IX_Orders_CustomerId ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_OrderDate_CustomerId ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_CustomerId_OrderDate ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_Status_OrderDate ON Sales.Orders;
DROP INDEX IF EXISTS IX_Orders_Open ON Sales.Orders;
DROP INDEX IF EXISTS NCCI_Orders_Reporting ON Sales.Orders;
