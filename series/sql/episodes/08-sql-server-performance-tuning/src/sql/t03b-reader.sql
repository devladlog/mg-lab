-- t03b-reader.sql
-- SQL Server only. Window 2: "the report". One row, read by its key. Under the default READ COMMITTED isolation level
-- it needs a shared lock on the row, and the row is locked exclusively by window 1: it waits. The comment is a marker.
SELECT Status FROM Sales.Orders WHERE OrderId = 1 /* mglab-blocked-report */;
