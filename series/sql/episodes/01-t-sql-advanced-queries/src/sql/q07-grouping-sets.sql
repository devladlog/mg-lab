-- q07: detail, subtotal per region and grand total in one pass with GROUPING SETS.
-- GROUPING() tells a subtotal NULL apart from a real NULL.
SELECT CASE WHEN GROUPING(c.Region) = 1 THEN N'All regions' ELSE c.Region END AS Region,
       CASE WHEN GROUPING(DATEPART(quarter, o.OrderDate)) = 1 THEN N'All quarters'
            ELSE CONCAT(N'Q', DATEPART(quarter, o.OrderDate)) END AS Quarter,
       COUNT(*)           AS Orders,
       SUM(o.TotalAmount) AS Revenue
FROM Sales.Orders AS o
JOIN Sales.Customers AS c ON c.CustomerId = o.CustomerId
GROUP BY GROUPING SETS ((c.Region, DATEPART(quarter, o.OrderDate)), (c.Region), ())
ORDER BY GROUPING(c.Region), c.Region, GROUPING(DATEPART(quarter, o.OrderDate)), DATEPART(quarter, o.OrderDate);
