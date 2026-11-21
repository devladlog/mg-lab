-- t04b-wait-delta-after-rcsi.sql
-- SQL Server only. The same comparison for the second run, with READ_COMMITTED_SNAPSHOT ON (the runner takes
-- 'before-rcsi' after the setting is on and 'after-rcsi' when the second run is over): no lock wait for the reader.
EXEC Tune.usp_WaitDelta @FromLabel = N'before-rcsi', @ToLabel = N'after-rcsi', @Top = 5;
