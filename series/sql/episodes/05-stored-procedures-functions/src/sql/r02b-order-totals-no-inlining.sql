-- r02b-order-totals-no-inlining.sql
-- The same query with inlining switched off for this statement only: same rows, and the actual plan
-- now calls the function (a UserDefinedFunction node), once per row.
SELECT o.OrderId,
       c.CustomerName,
       SUM(Sales.ufn_LineTotal(l.Qty, l.UnitPrice, l.DiscountPct)) AS OrderTotal
FROM Sales.Orders AS o
JOIN Sales.Customers AS c ON c.CustomerId = o.CustomerId
JOIN Sales.OrderLines AS l ON l.OrderId = o.OrderId
GROUP BY o.OrderId, c.CustomerName
ORDER BY o.OrderId
OPTION (USE HINT('DISABLE_TSQL_SCALAR_UDF_INLINING'));
