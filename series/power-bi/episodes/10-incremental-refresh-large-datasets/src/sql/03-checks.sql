-- What the load produced. Compare with: python3 tools/sql_mirror.py --rows 2000000
SELECT YEAR(OrderTimestamp) AS order_year, COUNT_BIG(*) AS order_lines, COUNT_BIG(DISTINCT OrderNumber) AS orders,
       SUM(CAST(Quantity AS decimal(18,2)) * UnitPrice) AS sales_amount
FROM dbo.Sales
GROUP BY YEAR(OrderTimestamp)
ORDER BY order_year;
GO
SELECT COUNT_BIG(*) AS order_lines, MIN(OrderTimestamp) AS first_order, MAX(OrderTimestamp) AS last_order FROM dbo.Sales;
GO
