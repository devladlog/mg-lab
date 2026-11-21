-- q02a: the two biggest orders per customer, with ROW_NUMBER.
-- OrderId is the tie-breaker: customer 1 has two orders of 1,250.00.
WITH ranked AS (
    SELECT o.CustomerId, o.OrderId, o.TotalAmount,
           ROW_NUMBER() OVER (PARTITION BY o.CustomerId
                              ORDER BY o.TotalAmount DESC, o.OrderId) AS rn
    FROM Sales.Orders AS o
)
SELECT c.CustomerName, r.OrderId, r.TotalAmount
FROM ranked AS r
JOIN Sales.Customers AS c ON c.CustomerId = r.CustomerId
WHERE r.rn <= 2
ORDER BY c.CustomerName, r.TotalAmount DESC, r.OrderId;
