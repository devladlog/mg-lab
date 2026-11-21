-- d03-naive-out-of-stock.sql
-- Carla Example orders three Carbon Wheelsets (two in stock) and a Bike Lock, through the NAIVE procedure.
-- Batch 1 fails with the CHECK constraint error. Batch 2 shows what was left behind.
SET NOCOUNT ON;
DECLARE @lines Sales.OrderLineList;
INSERT INTO @lines (ProductId, Qty) VALUES (4, 3), (3, 1);

DECLARE @newOrderId int;
EXEC Sales.usp_PlaceOrder_Naive @CustomerId = 4, @Lines = @lines, @OrderId = @newOrderId OUTPUT;
GO

SELECT (SELECT COUNT(*) FROM Sales.Orders WHERE CustomerId = 4 AND OrderId >= 2001) AS NewOrders,
       (SELECT COUNT(*) FROM Sales.OrderLines AS l JOIN Sales.Orders AS o ON o.OrderId = l.OrderId
         WHERE o.CustomerId = 4 AND o.OrderId >= 2001) AS NewOrderLines,
       (SELECT StockQty FROM Sales.Products WHERE ProductId = 4) AS WheelsetStock,
       (SELECT StockQty FROM Sales.Products WHERE ProductId = 3) AS LockStock,
       @@TRANCOUNT AS OpenTransactions;
