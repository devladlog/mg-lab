-- s07-masking.sql
-- analyst_demo (role reporting: SELECT on schema Sales, no UNMASK) reads the email column.
-- What the analyst saw is copied into a table variable (copies of masked data stay masked), then shown next
-- to what a db_owner member sees.
SET NOCOUNT ON;
DECLARE @seen TABLE (CustomerId int, CustomerName nvarchar(100), Email nvarchar(254));

EXECUTE AS USER = N'analyst_demo';
INSERT INTO @seen SELECT CustomerId, CustomerName, Email FROM Sales.Customers WHERE CustomerId <= 3;
REVERT;

SELECT s.CustomerName,
       s.Email AS AnalystSees,
       c.Email AS OwnerSees
FROM @seen AS s
JOIN Sales.Customers AS c ON c.CustomerId = s.CustomerId
ORDER BY s.CustomerId;
