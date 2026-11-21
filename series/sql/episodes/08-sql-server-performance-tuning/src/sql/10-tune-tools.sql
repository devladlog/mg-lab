-- 10-tune-tools.sql
-- SQL Server only (the local check runs the delta query inside Tune.usp_WaitDelta on DuckDB, with made-up snapshots).
-- Run in ContosoBikesPerf. Schema Tune: a table that keeps wait-statistics snapshots, a procedure that takes one,
-- and a procedure that subtracts two. sys.dm_os_wait_stats is cumulative since the instance started (or since
-- it was cleared), so one look at it says almost nothing: you need the difference between two snapshots.
-- Re-runnable.

-- sqlserver only
IF SCHEMA_ID(N'Tune') IS NULL
    EXEC (N'CREATE SCHEMA Tune');
GO

-- sqlserver only
DROP TABLE IF EXISTS Tune.WaitSnapshot;
GO

CREATE TABLE Tune.WaitSnapshot (
    Label            nvarchar(50) NOT NULL,
    WaitType         nvarchar(60) NOT NULL,
    WaitingTasks     bigint       NOT NULL,
    WaitTimeMs       bigint       NOT NULL,
    SignalWaitTimeMs bigint       NOT NULL,
    CONSTRAINT PK_WaitSnapshot PRIMARY KEY (Label, WaitType)
);
GO

-- sqlserver only
CREATE OR ALTER PROCEDURE Tune.usp_TakeWaitSnapshot
    @Label nvarchar(50)
AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM Tune.WaitSnapshot WHERE Label = @Label;
    INSERT INTO Tune.WaitSnapshot (Label, WaitType, WaitingTasks, WaitTimeMs, SignalWaitTimeMs)
    SELECT @Label, wait_type, waiting_tasks_count, wait_time_ms, signal_wait_time_ms
    FROM sys.dm_os_wait_stats
    WHERE waiting_tasks_count > 0;
END;
GO

-- sqlserver only
-- The ranking is a WATCH LIST, not an exclusion list: lock, buffer I/O and latch, log flush, CPU pressure, parallelism,
-- client and memory-grant waits (all described in Learn's sys.dm_os_wait_stats page). A server always has dozens
-- of background waits that add up to seconds in any window; Learn says queue waits belong to background tasks.
CREATE OR ALTER PROCEDURE Tune.usp_WaitDelta
    @FromLabel nvarchar(50),
    @ToLabel   nvarchar(50),
    @Top       int = 10
AS
BEGIN
    SET NOCOUNT ON;
    -- delta-query-begin
    SELECT TOP (@Top)
           e.WaitType,
           e.WaitingTasks - ISNULL(b.WaitingTasks, 0) AS WaitingTasksDelta,
           e.WaitTimeMs - ISNULL(b.WaitTimeMs, 0) AS WaitTimeMsDelta,
           e.SignalWaitTimeMs - ISNULL(b.SignalWaitTimeMs, 0) AS SignalWaitTimeMsDelta
    FROM Tune.WaitSnapshot AS e
    LEFT JOIN Tune.WaitSnapshot AS b ON b.WaitType = e.WaitType AND b.Label = @FromLabel
    WHERE e.Label = @ToLabel
      AND e.WaitTimeMs - ISNULL(b.WaitTimeMs, 0) > 0
      AND (LEFT(e.WaitType, 6) = N'LCK_M_' OR LEFT(e.WaitType, 12) = N'PAGEIOLATCH_' OR LEFT(e.WaitType, 10) = N'PAGELATCH_'
           OR e.WaitType IN (N'WRITELOG', N'SOS_SCHEDULER_YIELD', N'CXPACKET', N'CXCONSUMER', N'ASYNC_NETWORK_IO',
                             N'RESOURCE_SEMAPHORE', N'THREADPOOL'))
    ORDER BY WaitTimeMsDelta DESC;
    -- delta-query-end
END;
GO
