-- q02: the warehouse screen. Only 1% of orders are Open.
-- Open orders from June 2026 onwards: a small, well-defined subset of the table.
SELECT OrderId, CustomerId, OrderDate, TotalAmount
FROM Sales.Orders
WHERE Status = 'Open' AND OrderDate >= '2026-06-01'
ORDER BY OrderDate, OrderId;
