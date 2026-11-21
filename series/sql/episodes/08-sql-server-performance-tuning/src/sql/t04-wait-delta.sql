-- t04-wait-delta.sql
-- SQL Server only. The waits that completed between the snapshot taken before the blocking demo and the one taken
-- right after it (the runner takes them; in SSMS, run EXEC Tune.usp_TakeWaitSnapshot @Label = N'before-blocking' before
-- the demo and N'after-blocking' after it). The blocked reader's wait shows up as LCK_M_S, with the milliseconds it waited.
EXEC Tune.usp_WaitDelta @FromLabel = N'before-blocking', @ToLabel = N'after-blocking', @Top = 5;
