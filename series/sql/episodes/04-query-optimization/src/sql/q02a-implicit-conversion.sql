-- q02a: AccountNumber is varchar; int has higher data type precedence,
-- so SQL Server converts the COLUMN (CONVERT_IMPLICIT on every row).
-- The unique index on AccountNumber is sorted as text: it can't seek a number.
SELECT CustomerId, AccountNumber
FROM Sales.Customers
WHERE AccountNumber = 104242;
