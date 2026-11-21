-- What the gateway account can and can't do, and what the refresh must load. Run as the new login:
--   sqlcmd -S 10.50.0.30 -U pbi_gateway_reader -d ContosoBikesDW -i 02-checks.sql   (asks for the password)
-- Expected (tools/expected.py): 4,071 order lines, Sales Amount 1,862,401.98, 5 stores.
SELECT SUSER_NAME() AS LoginName, IS_MEMBER(N'db_datareader') AS CanRead, IS_MEMBER(N'db_datawriter') AS CanWrite;
SELECT COUNT_BIG(*) AS OrderLines, SUM(LineAmount) AS SalesAmount FROM dbo.FactSales;
SELECT s.Store, SUM(f.LineAmount) AS SalesAmount, COUNT_BIG(*) AS OrderLines
FROM dbo.FactSales AS f
JOIN dbo.DimStore AS s ON s.StoreKey = f.StoreKey
GROUP BY s.Store
ORDER BY s.Store;
GO
