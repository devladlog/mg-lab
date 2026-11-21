-- q06b: the same cross-tab with conditional aggregation (portable, and easy to add totals).
SELECT c.Region,
       SUM(CASE WHEN MONTH(o.OrderDate) = 1 THEN o.TotalAmount END) AS Jan,
       SUM(CASE WHEN MONTH(o.OrderDate) = 2 THEN o.TotalAmount END) AS Feb,
       SUM(CASE WHEN MONTH(o.OrderDate) = 3 THEN o.TotalAmount END) AS Mar,
       SUM(CASE WHEN MONTH(o.OrderDate) = 4 THEN o.TotalAmount END) AS Apr,
       SUM(CASE WHEN MONTH(o.OrderDate) = 5 THEN o.TotalAmount END) AS May,
       SUM(CASE WHEN MONTH(o.OrderDate) = 6 THEN o.TotalAmount END) AS Jun
FROM Sales.Orders AS o
JOIN Sales.Customers AS c ON c.CustomerId = o.CustomerId
GROUP BY c.Region
ORDER BY c.Region;
