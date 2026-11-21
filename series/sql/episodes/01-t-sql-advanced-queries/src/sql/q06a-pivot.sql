-- q06a: revenue per region and month as a cross-tab with PIVOT.
SELECT Region, [1] AS Jan, [2] AS Feb, [3] AS Mar, [4] AS Apr, [5] AS May, [6] AS Jun
FROM (
    SELECT c.Region, MONTH(o.OrderDate) AS OrderMonth, o.TotalAmount
    FROM Sales.Orders AS o
    JOIN Sales.Customers AS c ON c.CustomerId = o.CustomerId
) AS src
PIVOT (SUM(TotalAmount) FOR OrderMonth IN ([1], [2], [3], [4], [5], [6])) AS p
ORDER BY Region;
