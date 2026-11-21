-- s01-least-privilege.sql
-- sales_north (role app_sales) has EXECUTE on three procedures and nothing else.
-- Each attempt runs inside TRY/CATCH and leaves one row in @result; the last SELECT shows them.
SET NOCOUNT ON;
DECLARE @result TABLE (Step int, Caller sysname, Attempt nvarchar(80), Outcome nvarchar(20), Detail nvarchar(100));
DECLARE @rows TABLE (CustomerId int, CustomerName nvarchar(100), Region nvarchar(20));
DECLARE @n int;

EXECUTE AS USER = N'sales_north';

BEGIN TRY
    SELECT @n = COUNT(*) FROM Sales.Customers;
    INSERT INTO @result VALUES (1, USER_NAME(), N'SELECT FROM Sales.Customers', N'allowed', CONCAT(@n, N' rows'));
END TRY
BEGIN CATCH
    INSERT INTO @result VALUES (1, USER_NAME(), N'SELECT FROM Sales.Customers', N'denied', CONCAT(N'error ', ERROR_NUMBER()));
END CATCH;

BEGIN TRY
    INSERT INTO @rows EXEC Sales.usp_ListCustomers;
    INSERT INTO @result SELECT 2, USER_NAME(), N'EXEC Sales.usp_ListCustomers', N'allowed', CONCAT(COUNT(*), N' rows') FROM @rows;
END TRY
BEGIN CATCH
    INSERT INTO @result VALUES (2, USER_NAME(), N'EXEC Sales.usp_ListCustomers', N'denied', CONCAT(N'error ', ERROR_NUMBER()));
END CATCH;

BEGIN TRY
    DELETE FROM @rows;
    INSERT INTO @rows EXEC Sales.usp_SearchCustomers_Unsafe @NamePrefix = N'A';
    INSERT INTO @result VALUES (3, USER_NAME(), N'EXEC Sales.usp_SearchCustomers_Unsafe', N'allowed', N'');
END TRY
BEGIN CATCH
    INSERT INTO @result VALUES (3, USER_NAME(), N'EXEC Sales.usp_SearchCustomers_Unsafe', N'denied', CONCAT(N'error ', ERROR_NUMBER()));
END CATCH;

REVERT;

SELECT Caller, Attempt, Outcome, Detail FROM @result ORDER BY Step;
