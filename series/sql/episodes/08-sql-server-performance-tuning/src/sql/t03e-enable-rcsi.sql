-- t03e-enable-rcsi.sql
-- SQL Server only. The server-side fix for readers blocked by writers: READ_COMMITTED_SNAPSHOT. READ COMMITTED
-- statements then read the last committed version of a row (from the version store in tempdb) instead of taking
-- shared locks. Learn: there must be no other active connection in the database while this runs, so the statement
-- disconnects them (ROLLBACK IMMEDIATE). Rows get 14 extra bytes when modified, and tempdb holds the versions.
ALTER DATABASE ContosoBikesPerf SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
