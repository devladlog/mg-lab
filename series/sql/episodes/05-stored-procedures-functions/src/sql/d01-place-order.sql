-- d01-place-order.sql
-- Place an order for Rita Sample: two Trail Helmets and one Bike Lock at 10% off, in one call.
SET NOCOUNT ON;
DECLARE @lines Sales.OrderLineList;
INSERT INTO @lines (ProductId, Qty, DiscountPct) VALUES (1, 2, 0), (3, 1, 10);

DECLARE @newOrderId int;
EXEC Sales.usp_PlaceOrder @CustomerId = 2, @Lines = @lines, @OrderId = @newOrderId OUTPUT;

SELECT CASE WHEN @newOrderId >= 2001 THEN N'yes' ELSE N'no' END AS GotNewOrderId,
       s.Lines,
       s.OrderTotal,
       (SELECT StockQty FROM Sales.Products WHERE ProductId = 1) AS HelmetStock,
       (SELECT StockQty FROM Sales.Products WHERE ProductId = 3) AS LockStock
FROM Sales.ufn_CustomerOrderSummary(2) AS s
WHERE s.OrderId = @newOrderId;
