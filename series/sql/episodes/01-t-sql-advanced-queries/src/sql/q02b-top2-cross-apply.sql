-- q02b: the same question with CROSS APPLY + TOP: "for each customer, run this subquery".
SELECT c.CustomerName, t.OrderId, t.TotalAmount
FROM Sales.Customers AS c
CROSS APPLY (
    SELECT TOP (2) o.OrderId, o.TotalAmount
    FROM Sales.Orders AS o
    WHERE o.CustomerId = c.CustomerId
    ORDER BY o.TotalAmount DESC, o.OrderId
) AS t
ORDER BY c.CustomerName, t.TotalAmount DESC, t.OrderId;
