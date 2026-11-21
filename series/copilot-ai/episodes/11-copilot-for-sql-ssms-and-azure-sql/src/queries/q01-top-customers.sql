-- q01: "Top 5 customers by revenue in September 2026, cancelled orders excluded."
SELECT TOP (5)
       c.CustomerId,
       c.CustomerName,
       SUM(l.Quantity * l.UnitPrice) AS Revenue
FROM Sales.Customers  AS c
JOIN Sales.Orders     AS o ON o.CustomerId = c.CustomerId
JOIN Sales.OrderLines AS l ON l.OrderId    = o.OrderId
WHERE o.Status <> N'Cancelled'
  AND o.OrderDate >= '2026-09-01'
  AND o.OrderDate <  '2026-10-01'
GROUP BY c.CustomerId, c.CustomerName
ORDER BY Revenue DESC, c.CustomerId;
