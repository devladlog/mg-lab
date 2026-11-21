-- d04-safe-out-of-stock.sql
-- Bruno Test sends the same order through the SAFE procedure. Batch 1 fails with the same error,
-- re-raised by THROW. Batch 2: nothing was written.
SET NOCOUNT ON;
DECLARE @lines Sales.OrderLineList;
INSERT INTO @lines (ProductId, Qty) VALUES (4, 3), (3, 1);

DECLARE @newOrderId int;
EXEC Sales.usp_PlaceOrder @CustomerId = 3, @Lines = @lines, @OrderId = @newOrderId OUTPUT;
GO

SELECT (SELECT COUNT(*) FROM Sales.Orders WHERE CustomerId = 3 AND OrderId >= 2001) AS NewOrders,
       (SELECT COUNT(*) FROM Sales.OrderLines AS l JOIN Sales.Orders AS o ON o.OrderId = l.OrderId
         WHERE o.CustomerId = 3 AND o.OrderId >= 2001) AS NewOrderLines,
       (SELECT StockQty FROM Sales.Products WHERE ProductId = 4) AS WheelsetStock,
       (SELECT StockQty FROM Sales.Products WHERE ProductId = 3) AS LockStock,
       @@TRANCOUNT AS OpenTransactions;
