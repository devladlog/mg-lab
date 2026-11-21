-- h02-init-standby.sql
-- SQL Server only. Log shipping step 0: a full backup of the primary, restored as ContosoBikesHA_Standby WITH STANDBY.
-- STANDBY leaves the copy readable (read-only) between log restores; the undo file keeps what is needed to undo
-- the recovery effects, and the next RESTORE deletes it. RESTORE ... MOVE takes string literals only, so that one
-- statement is built as text from the instance's default folders (the standby's files carry its own name).
USE master;
GO
DECLARE @sep nchar(1) = CONVERT(nchar(1), SERVERPROPERTY(N'PathSeparator'));
DECLARE @bak nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultBackupPath'));
IF RIGHT(@bak, 1) <> @sep SET @bak += @sep;
DECLARE @dat nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultDataPath'));
IF RIGHT(@dat, 1) <> @sep SET @dat += @sep;
DECLARE @log nvarchar(260) = CONVERT(nvarchar(260), SERVERPROPERTY(N'InstanceDefaultLogPath'));
IF RIGHT(@log, 1) <> @sep SET @log += @sep;
DECLARE @full nvarchar(300) = @bak + N'MGLab_ContosoBikesHA_Full.bak';
BACKUP DATABASE ContosoBikesHA TO DISK = @full WITH INIT, CHECKSUM, COMPRESSION, STATS = 50;
DECLARE @q nchar(1) = N'''';
DECLARE @mdf nvarchar(300) = @q + REPLACE(@dat + N'MGLab_ContosoBikesHA_Standby.mdf', @q, @q + @q) + @q;
DECLARE @ldf nvarchar(300) = @q + REPLACE(@log + N'MGLab_ContosoBikesHA_Standby_log.ldf', @q, @q + @q) + @q;
DECLARE @undo nvarchar(300) = @q + REPLACE(@dat + N'MGLab_ContosoBikesHA_Standby.undo', @q, @q + @q) + @q;
DECLARE @sql nvarchar(max) = CONCAT(N'RESTORE DATABASE ContosoBikesHA_Standby FROM DISK = ', @q, @full, @q,
    N' WITH MOVE N''ContosoBikesHA'' TO ', @mdf, N', MOVE N''ContosoBikesHA_log'' TO ', @ldf,
    N', STANDBY = ', @undo, N', CHECKSUM, STATS = 50;');
EXEC sys.sp_executesql @sql;
GO
SELECT N'Standby state' AS Item,
       CONVERT(nvarchar(60), CONCAT(state_desc, CASE WHEN is_in_standby = 1 THEN N' (read-only standby)' ELSE N'' END)) AS Result
FROM sys.databases WHERE name = N'ContosoBikesHA_Standby'
UNION ALL
SELECT N'Orders on the primary', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesHA.Sales.Orders
UNION ALL
SELECT N'Orders on the standby', CONVERT(nvarchar(60), COUNT(*)) FROM ContosoBikesHA_Standby.Sales.Orders;
GO
