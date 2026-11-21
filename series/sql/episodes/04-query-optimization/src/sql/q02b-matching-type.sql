-- q02b: a value of the column's own type: one seek.
SELECT CustomerId, AccountNumber
FROM Sales.Customers
WHERE AccountNumber = '104242';
