-- Start a measurement from zero: clears the plan cache of THIS database only (the lab SQL Server is shared, so no DBCC FREEPROCCACHE).
-- Run it, then run one DAX query in Desktop, then run 06-observe-directquery.sql.
USE [ContosoBikesDW];
GO
ALTER DATABASE SCOPED CONFIGURATION CLEAR PROCEDURE_CACHE;
GO
