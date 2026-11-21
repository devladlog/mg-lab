-- r02a-order-totals.sql
-- Order totals through the scalar UDF. With inlining, the UDF's expression becomes part of this query:
-- the actual plan has no UserDefinedFunction node.
SELECT o.OrderId,
       c.CustomerName,
       SUM(Sales.ufn_LineTotal(l.Qty, l.UnitPrice, l.DiscountPct)) AS OrderTotal
FROM Sales.Orders AS o
JOIN Sales.Customers AS c ON c.CustomerId = o.CustomerId
JOIN Sales.OrderLines AS l ON l.OrderId = o.OrderId
GROUP BY o.OrderId, c.CustomerName
ORDER BY o.OrderId;
