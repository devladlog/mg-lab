-- b05-incident.sql
-- The accident. Somebody runs an UPDATE without a WHERE clause, and one legitimate order arrives afterwards.
-- 1. we write down the time just before (a real incident has no such note: you read it off the user's
--    report, the application log or the log backup itself), 2. the bad UPDATE, 3. a good order,
-- 4. a log backup that holds all of it. Batches marked "sqlserver only" are skipped by the local DuckDB check.

-- sqlserver only
USE ContosoBikesBackup;
IF OBJECT_ID(N'dbo.RecoveryMarks') IS NULL
    CREATE TABLE dbo.RecoveryMarks (
        Name     nvarchar(50) NOT NULL CONSTRAINT PK_RecoveryMarks PRIMARY KEY,
        MarkTime datetime     NOT NULL
    );
GO

-- sqlserver only
-- wait a second so that every earlier commit is clearly before the mark, and the mark clearly before the UPDATE
WAITFOR DELAY '00:00:01';
INSERT INTO dbo.RecoveryMarks (Name, MarkTime) VALUES (N'before-bad-update', GETDATE());
WAITFOR DELAY '00:00:02';
GO

-- The accident: the WHERE clause is missing, every product is now free.
UPDATE Sales.Products SET ListPrice = 0;
GO

-- sqlserver only
WAITFOR DELAY '00:00:01';
GO

-- Business goes on: a legitimate order after the accident.
INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1012, 4, '2025-05-20', N'Placed');
INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct) VALUES
    (1012, 1, 2, 1, 0.00, 0.00);
GO

-- sqlserver only
DECLARE @dir nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@dir, 1) <> CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'))
    SET @dir += CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @file nvarchar(300) = @dir + N'MGLab_ContosoBikesBackup_Log2.trn';
BACKUP LOG ContosoBikesBackup TO DISK = @file WITH INIT, CHECKSUM, COMPRESSION, STATS = 50;
GO

SELECT N'Products priced at 0' AS Item, COUNT(*) AS Result FROM Sales.Products WHERE ListPrice = 0
UNION ALL
SELECT N'Orders in the live database', COUNT(*) FROM Sales.Orders;
GO
