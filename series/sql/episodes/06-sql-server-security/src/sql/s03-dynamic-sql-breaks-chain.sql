-- s03-dynamic-sql-breaks-chain.sql
-- The parameterized search, called by sales_north BEFORE the procedure is signed. The dynamic SQL inside
-- sp_executesql is a separate batch: the ownership chain stops there and SQL Server checks the caller's own
-- SELECT permission on Sales.Customers, which sales_north doesn't have.
SET NOCOUNT ON;
DECLARE @found TABLE (CustomerId int, CustomerName nvarchar(100), Region nvarchar(20));
DECLARE @result TABLE (Attempt int, Caller sysname, Input nvarchar(100), Outcome nvarchar(20), RowsReturned int, ErrorNumber int);

EXECUTE AS USER = N'sales_north';

BEGIN TRY
    INSERT INTO @found EXEC Sales.usp_SearchCustomers @NamePrefix = N'Alex';
    INSERT INTO @result SELECT 1, USER_NAME(), N'Alex', N'allowed', COUNT(*), NULL FROM @found;
END TRY
BEGIN CATCH
    INSERT INTO @result VALUES (1, USER_NAME(), N'Alex', N'denied', NULL, ERROR_NUMBER());
END CATCH;

BEGIN TRY
    DELETE FROM @found;
    INSERT INTO @found EXEC Sales.usp_SearchCustomers @NamePrefix = N''' OR 1 = 1 --';
    INSERT INTO @result SELECT 2, USER_NAME(), N''' OR 1 = 1 --', N'allowed', COUNT(*), NULL FROM @found;
END TRY
BEGIN CATCH
    INSERT INTO @result VALUES (2, USER_NAME(), N''' OR 1 = 1 --', N'denied', NULL, ERROR_NUMBER());
END CATCH;

REVERT;

SELECT Caller, Input, Outcome, RowsReturned, ErrorNumber FROM @result ORDER BY Attempt;
