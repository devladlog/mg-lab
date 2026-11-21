-- t03a-blocker.sql
-- SQL Server only. Window 1: "the application". It changes a row and then... does something else (calls a web service,
-- waits for a user) before it commits. The transaction stays open, and so does the exclusive lock on the row.
BEGIN TRANSACTION;
UPDATE Sales.Orders SET Status = 'Cancelled' WHERE OrderId = 1;
