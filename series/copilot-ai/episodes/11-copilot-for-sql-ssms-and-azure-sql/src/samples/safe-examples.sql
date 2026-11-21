-- Hand-written T-SQL that the gate should pass in read-only mode (tests/test_gate.py). Not Copilot output.
SELECT TOP (10) c.CustomerId, c.CustomerName
FROM Sales.Customers AS c
ORDER BY c.CustomerName;
GO
WITH monthly AS (
    SELECT DATEFROMPARTS(YEAR(o.OrderDate), MONTH(o.OrderDate), 1) AS MonthStart, COUNT(*) AS Orders
    FROM Sales.Orders AS o
    GROUP BY DATEFROMPARTS(YEAR(o.OrderDate), MONTH(o.OrderDate), 1)
)
SELECT MonthStart, Orders FROM monthly ORDER BY MonthStart;
GO
SELECT name, compatibility_level FROM sys.databases WHERE name = DB_NAME();
EXEC sp_help N'Sales.Orders';
