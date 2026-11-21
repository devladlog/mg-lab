-- q01a: YEAR() and MONTH() run on every OrderDate before the comparison:
-- the index on OrderDate can't jump to March. SQL Server reads all of it.
SELECT COUNT(*) AS Orders, SUM(TotalAmount) AS Revenue
FROM Sales.Orders
WHERE YEAR(OrderDate) = 2025
  AND MONTH(OrderDate) = 3;
