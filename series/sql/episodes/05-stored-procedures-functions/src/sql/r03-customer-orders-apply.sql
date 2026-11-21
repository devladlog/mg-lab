-- r03-customer-orders-apply.sql
-- The inline TVF used like a parameterized view: one call per customer with CROSS APPLY.
SELECT c.CustomerName,
       s.OrderId,
       s.OrderDate,
       s.Lines,
       s.OrderTotal
FROM Sales.Customers AS c
CROSS APPLY Sales.ufn_CustomerOrderSummary(c.CustomerId) AS s
WHERE c.Region = N'North'
ORDER BY c.CustomerName, s.OrderId;
