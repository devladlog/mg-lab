-- b07-verify-and-repair.sql
-- SQL Server only (the repair batch and the result are also run, on a model, by the local check).
-- 1. DBCC CHECKDB on the restored copy: a restore that succeeds can still contain a damaged database.
-- 2. RESTORE VERIFYONLY ... WITH CHECKSUM on the full backup: it reads the backup and checks the backup checksum.
--    It does not check the data inside, which is why step 1 exists.
-- 3. Repair the live database FROM THE COPY (written without UPDATE ... FROM so DuckDB runs it too): put the prices back and keep order 1012, which an overwrite
--    with the restored database would have thrown away.
-- sqlserver only
USE master;
DBCC CHECKDB (N'ContosoBikesRecovered') WITH NO_INFOMSGS, ALL_ERRORMSGS;
GO

-- sqlserver only
DECLARE @dir nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@dir, 1) <> CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'))
    SET @dir += CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @file nvarchar(300) = @dir + N'MGLab_ContosoBikesBackup_Full.bak';
RESTORE VERIFYONLY FROM DISK = @file WITH CHECKSUM;
GO

UPDATE ContosoBikesBackup.Sales.Products
SET ListPrice = (SELECT rec.ListPrice FROM ContosoBikesRecovered.Sales.Products AS rec
                 WHERE rec.ProductId = Products.ProductId)
WHERE EXISTS (SELECT 1 FROM ContosoBikesRecovered.Sales.Products AS rec
              WHERE rec.ProductId = Products.ProductId AND rec.ListPrice <> Products.ListPrice);
GO

SELECT N'Products priced at 0 in the live database' AS Item, COUNT(*) AS Result FROM ContosoBikesBackup.Sales.Products WHERE ListPrice = 0
UNION ALL
SELECT N'Prices equal to the copy', COUNT(*) FROM ContosoBikesBackup.Sales.Products AS live
    JOIN ContosoBikesRecovered.Sales.Products AS rec ON rec.ProductId = live.ProductId AND rec.ListPrice = live.ListPrice
UNION ALL
SELECT N'Orders in the live database', COUNT(*) FROM ContosoBikesBackup.Sales.Orders;
GO
