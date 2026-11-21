-- q08: the gotcha. With ORDER BY and no frame, SUM() OVER uses RANGE UNBOUNDED PRECEDING AND CURRENT ROW,
-- and RANGE includes every row with the same OrderDate: both orders of 2025-01-15 get the same "running" total.
-- Fix: say ROWS, and add a unique tie-breaker (OrderId).
SELECT OrderId, OrderDate, TotalAmount,
       SUM(TotalAmount) OVER (ORDER BY OrderDate)                    AS DefaultFrame,
       SUM(TotalAmount) OVER (ORDER BY OrderDate, OrderId
                              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS RowsFrame
FROM Sales.Orders
WHERE OrderDate < '2025-03-01'
ORDER BY OrderDate, OrderId;
