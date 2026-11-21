-- q03: "Which customers have never ordered?"
SELECT c.CustomerId, c.CustomerName
FROM Sales.Customers AS c
WHERE NOT EXISTS (SELECT 1 FROM Sales.Orders AS o WHERE o.CustomerId = c.CustomerId)
ORDER BY c.CustomerId;
