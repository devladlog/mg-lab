-- Row counts and totals of the detail table and of the aggregation view. Compare with tools/expected.py:
--   as loaded            4,071 order lines, Sales Amount 1,862,401.98, Units 7,462, aggregation rows 3,947
--   after 04-scale-up    2,035,500 order lines, Sales Amount 931,200,990.00, Units 3,731,000, aggregation rows 3,947
USE [ContosoBikesDW];
GO
SELECT COUNT_BIG(*) AS OrderLines, SUM(LineAmount) AS SalesAmount, SUM(CAST(Quantity AS bigint)) AS Units FROM dbo.FactSales;
SELECT COUNT_BIG(*) AS AggregationRows, SUM(LineAmount) AS SalesAmount, SUM(CAST(Units AS bigint)) AS Units, SUM(OrderLines) AS OrderLines FROM dbo.vwSalesAgg;
GO
