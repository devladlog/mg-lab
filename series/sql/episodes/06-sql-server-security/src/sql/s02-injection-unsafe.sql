-- s02-injection-unsafe.sql
-- Run as a db_owner member: what too many applications connect as. A name prefix should match one customer;
-- a crafted "name" closes the string literal and turns the WHERE clause into OR 1 = 1.
SET NOCOUNT ON;
DECLARE @found TABLE (CustomerId int, CustomerName nvarchar(100), Region nvarchar(20));
DECLARE @result TABLE (Attempt int, Input nvarchar(100), RowsReturned int);

INSERT INTO @found EXEC Sales.usp_SearchCustomers_Unsafe @NamePrefix = N'Alex';
INSERT INTO @result SELECT 1, N'Alex', COUNT(*) FROM @found;
DELETE FROM @found;

INSERT INTO @found EXEC Sales.usp_SearchCustomers_Unsafe @NamePrefix = N''' OR 1 = 1 --';
INSERT INTO @result SELECT 2, N''' OR 1 = 1 --', COUNT(*) FROM @found;

SELECT Input, RowsReturned FROM @result ORDER BY Attempt;
