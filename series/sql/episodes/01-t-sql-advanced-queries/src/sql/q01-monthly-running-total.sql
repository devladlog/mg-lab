-- q01: monthly revenue per region, running total and change vs previous month.
-- LAG looks at the previous ROW: Centre has no April orders, so its May row compares with March.
-- DATETRUNC and the WINDOW clause need SQL Server 2022 (compatibility level 160) or Azure SQL.
WITH monthly AS (
    SELECT c.Region,
           DATETRUNC(month, o.OrderDate) AS MonthStart,
           SUM(o.TotalAmount)            AS Revenue
    FROM Sales.Orders AS o
    JOIN Sales.Customers AS c ON c.CustomerId = o.CustomerId
    GROUP BY c.Region, DATETRUNC(month, o.OrderDate)
)
SELECT Region,
       MonthStart,
       Revenue,
       SUM(Revenue) OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS RunningRevenue,
       Revenue - LAG(Revenue) OVER w                                          AS ChangeVsPrev
FROM monthly
WINDOW w AS (PARTITION BY Region ORDER BY MonthStart)
ORDER BY Region, MonthStart;
