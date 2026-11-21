-- t03d-release.sql
-- SQL Server only. Window 1 again: the "application" gives up. A rollback puts the row back and releases the lock.
ROLLBACK TRANSACTION;
