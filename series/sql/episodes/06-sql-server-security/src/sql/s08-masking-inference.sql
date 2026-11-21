-- s08-masking-inference.sql
-- The gotcha Learn documents: masking changes what a query RETURNS, not what its WHERE clause can test.
-- With ad hoc SELECT rights the analyst can guess the real address, one letter at a time.
SET NOCOUNT ON;
DECLARE @result TABLE (Step int, Guess nvarchar(100), RowsMatched int);

EXECUTE AS USER = N'analyst_demo';
INSERT INTO @result SELECT 1, N'c%',       COUNT(*) FROM Sales.Customers WHERE Email LIKE N'c%';
INSERT INTO @result SELECT 2, N'carla.e%', COUNT(*) FROM Sales.Customers WHERE Email LIKE N'carla.e%';
INSERT INTO @result SELECT 3, N'carla.x%', COUNT(*) FROM Sales.Customers WHERE Email LIKE N'carla.x%';
REVERT;

SELECT Guess, RowsMatched FROM @result ORDER BY Step;
