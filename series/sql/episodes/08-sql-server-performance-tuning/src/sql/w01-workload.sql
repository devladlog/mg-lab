-- w01-workload.sql
-- SQL Server only. A small, repeatable workload with markers in the query text (a /* ... */ comment is part of the
-- text, so the DMVs show it). 3 full scans (the date function on the column cannot use an index) and 50 single-row
-- lookups by key. ALTER DATABASE SCOPED CONFIGURATION ... CLEAR PROCEDURE_CACHE empties this database's plans so the
-- counts start at zero without touching the rest of the instance.
ALTER DATABASE SCOPED CONFIGURATION CLEAR PROCEDURE_CACHE;
GO
DECLARE @n int, @i int = 1;
WHILE @i <= 3
BEGIN
    EXEC sys.sp_executesql N'SELECT @n = COUNT(*) FROM Sales.Orders WHERE YEAR(OrderDate) = 2025 /* mglab-w-scan */;', N'@n int OUTPUT', @n = @n OUTPUT;
    SET @i += 1;
END;
GO
DECLARE @status varchar(10), @id int = 1;
WHILE @id <= 50
BEGIN
    EXEC sys.sp_executesql N'SELECT @status = Status FROM Sales.Orders WHERE OrderId = @id /* mglab-w-seek */;', N'@id int, @status varchar(10) OUTPUT', @id = @id, @status = @status OUTPUT;
    SET @id += 1;
END;
GO
