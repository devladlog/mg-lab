-- q03: revenue per year and sales channel, over all 200,000 orders.
-- No WHERE clause: no B-tree index can turn this into a seek. It reads every row.
SELECT YEAR(OrderDate) AS OrderYear, Channel,
       COUNT(*) AS Orders, SUM(TotalAmount) AS Revenue
FROM Sales.Orders
GROUP BY YEAR(OrderDate), Channel
ORDER BY OrderYear, Channel;
