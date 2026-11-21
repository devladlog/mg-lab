-- 11-app-procedures.sql
-- SQL Server only. The procedures the application calls (plus one it must never have).

-- Static SQL: the caller needs EXECUTE on the procedure and nothing on the table (ownership chaining:
-- procedure and table have the same owner, dbo, so SQL Server doesn't check table permissions).
CREATE OR ALTER PROCEDURE Sales.usp_ListCustomers
AS
BEGIN
    SET NOCOUNT ON;
    SELECT CustomerId, CustomerName, Region
    FROM Sales.Customers
    ORDER BY CustomerId;
END;
GO

-- DON'T: user input concatenated into the SQL text.
CREATE OR ALTER PROCEDURE Sales.usp_SearchCustomers_Unsafe
    @NamePrefix nvarchar(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @sql nvarchar(max) =
        N'SELECT CustomerId, CustomerName, Region FROM Sales.Customers WHERE CustomerName LIKE N'''
        + @NamePrefix + N'%'' ORDER BY CustomerId;';
    EXEC (@sql);
END;
GO

-- DO: the SQL text is fixed and the value travels as a typed parameter of sp_executesql.
-- Only the sort column varies, picked from a whitelist and quoted with QUOTENAME.
CREATE OR ALTER PROCEDURE Sales.usp_SearchCustomers
    @NamePrefix nvarchar(100),
    @SortBy     sysname = N'CustomerId'
AS
BEGIN
    SET NOCOUNT ON;
    IF @SortBy NOT IN (N'CustomerId', N'CustomerName', N'Region')
        THROW 50010, N'Unsupported sort column.', 1;
    DECLARE @sql nvarchar(max) =
        N'SELECT CustomerId, CustomerName, Region FROM Sales.Customers WHERE CustomerName LIKE @prefix + N''%'' ORDER BY '
        + QUOTENAME(@SortBy) + N';';
    EXEC sys.sp_executesql @sql, N'@prefix nvarchar(100)', @prefix = @NamePrefix;
END;
GO
