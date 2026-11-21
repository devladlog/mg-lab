-- q01b: the same question as a range on the bare column. The index can seek.
-- Half-open interval (>= first day, < first day of next month): right for date and datetime columns.
SELECT COUNT(*) AS Orders, SUM(TotalAmount) AS Revenue
FROM Sales.Orders
WHERE OrderDate >= '2025-03-01'
  AND OrderDate <  '2025-04-01';
