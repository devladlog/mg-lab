-- q03: latest order per customer. OUTER APPLY keeps customers with no orders (NULLs);
-- CROSS APPLY would drop them.
SELECT c.CustomerName, c.Region, lo.OrderId, lo.OrderDate, lo.TotalAmount
FROM Sales.Customers AS c
OUTER APPLY (
    SELECT TOP (1) o.OrderId, o.OrderDate, o.TotalAmount
    FROM Sales.Orders AS o
    WHERE o.CustomerId = c.CustomerId
    ORDER BY o.OrderDate DESC, o.OrderId DESC
) AS lo
ORDER BY c.CustomerName;
