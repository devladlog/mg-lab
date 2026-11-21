-- b06-restore-copy.sql
-- SQL Server only. Restore the chain into a COPY, ContosoBikesRecovered, up to the moment before the accident.
-- The live database is never touched. full -> differential -> log 1 -> log 2, all WITH NORECOVERY and the same
-- STOPAT, then one separate RESTORE ... WITH RECOVERY (the order and the final step are Learn's best practice).
-- RESTORE ... MOVE takes string literals only, so each statement is built as text from the instance's
-- default folders. The new files are named after the copy, so nothing collides with the live files.
USE master;
GO
DECLARE @sep nchar(1) = CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @bak nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@bak, 1) <> @sep SET @bak += @sep;
DECLARE @dat nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultDataPath'));
IF RIGHT(@dat, 1) <> @sep SET @dat += @sep;
DECLARE @log nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultLogPath'));
IF RIGHT(@log, 1) <> @sep SET @log += @sep;
DECLARE @q nchar(1) = N'''';
DECLARE @stop datetime = (SELECT MarkTime FROM ContosoBikesBackup.dbo.RecoveryMarks WHERE Name = N'before-bad-update');
DECLARE @stopText nvarchar(30) = @q + CONVERT(nvarchar(23), @stop, 126) + @q;
DECLARE @mdf nvarchar(300) = @q + REPLACE(@dat + N'MGLab_ContosoBikesRecovered.mdf', @q, @q + @q) + @q;
DECLARE @ldf nvarchar(300) = @q + REPLACE(@log + N'MGLab_ContosoBikesRecovered_log.ldf', @q, @q + @q) + @q;
DECLARE @chain TABLE (Seq int NOT NULL PRIMARY KEY, Stmt nvarchar(max) NOT NULL);
INSERT INTO @chain (Seq, Stmt) VALUES
    (1, CONCAT(N'RESTORE DATABASE ContosoBikesRecovered FROM DISK = ', @q, @bak, N'MGLab_ContosoBikesBackup_Full.bak', @q,
               N' WITH MOVE N''ContosoBikesBackup'' TO ', @mdf, N', MOVE N''ContosoBikesBackup_log'' TO ', @ldf,
               N', NORECOVERY, CHECKSUM, STOPAT = ', @stopText, N';')),
    (2, CONCAT(N'RESTORE DATABASE ContosoBikesRecovered FROM DISK = ', @q, @bak, N'MGLab_ContosoBikesBackup_Diff.bak', @q,
               N' WITH NORECOVERY, CHECKSUM, STOPAT = ', @stopText, N';')),
    (3, CONCAT(N'RESTORE LOG ContosoBikesRecovered FROM DISK = ', @q, @bak, N'MGLab_ContosoBikesBackup_Log1.trn', @q,
               N' WITH NORECOVERY, CHECKSUM, STOPAT = ', @stopText, N';')),
    (4, CONCAT(N'RESTORE LOG ContosoBikesRecovered FROM DISK = ', @q, @bak, N'MGLab_ContosoBikesBackup_Log2.trn', @q,
               N' WITH NORECOVERY, CHECKSUM, STOPAT = ', @stopText, N';')),
    (5, N'RESTORE DATABASE ContosoBikesRecovered WITH RECOVERY;');
DECLARE @seq int = 1, @sql nvarchar(max);
WHILE @seq <= 5
BEGIN
    SELECT @sql = Stmt FROM @chain WHERE Seq = @seq;
    EXEC sys.sp_executesql @sql;
    SET @seq += 1;
END;
GO
SELECT N'Recovered copy state' AS Item, CONVERT(nvarchar(20), state_desc) AS Result
FROM sys.databases WHERE name = N'ContosoBikesRecovered'
UNION ALL
SELECT N'Products priced at 0 in the copy', CONVERT(nvarchar(20), COUNT(*)) FROM ContosoBikesRecovered.Sales.Products WHERE ListPrice = 0
UNION ALL
SELECT N'Orders in the copy', CONVERT(nvarchar(20), COUNT(*)) FROM ContosoBikesRecovered.Sales.Orders
UNION ALL
SELECT N'Order 1012 in the copy', CONVERT(nvarchar(20), COUNT(*)) FROM ContosoBikesRecovered.Sales.Orders WHERE OrderId = 1012;
GO
