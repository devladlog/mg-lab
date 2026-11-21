-- r03-sales-by-product.sql
-- SQL Server only. What the report's dataset returns for the default parameters: the first thing to run
-- when a report shows the wrong numbers, before blaming the report.
USE ContosoBikesRpt;
GO
EXEC Rpt.usp_SalesByProduct @From = '2025-03-01', @To = '2025-04-30', @Region = N'ALL';
GO
