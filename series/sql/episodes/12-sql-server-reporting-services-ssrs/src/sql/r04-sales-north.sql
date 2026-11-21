-- r04-sales-north.sql
-- SQL Server only. The same range for one region: the value the Region drop-down passes.
USE ContosoBikesRpt;
GO
EXEC Rpt.usp_SalesByProduct @From = '2025-03-01', @To = '2025-04-30', @Region = N'North';
GO
