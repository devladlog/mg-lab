-- t05-cleanup.sql
-- SQL Server only. Tear-down: row versioning off again, and the Tune objects removed.
ALTER DATABASE ContosoBikesPerf SET READ_COMMITTED_SNAPSHOT OFF WITH ROLLBACK IMMEDIATE;
GO
DROP PROCEDURE IF EXISTS Tune.usp_WaitDelta;
DROP PROCEDURE IF EXISTS Tune.usp_TakeWaitSnapshot;
DROP TABLE IF EXISTS Tune.WaitSnapshot;
GO
DROP SCHEMA IF EXISTS Tune;
GO
