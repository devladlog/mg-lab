-- r01-report-objects.sql
-- Run in ContosoBikesRpt after 01-schema-and-data.sql. Re-runnable.
-- Two stored procedures are the whole data layer of the report SalesByProduct.rdl: the report server account
-- only needs EXECUTE on schema Rpt, never SELECT on the order tables.
-- The SELECT between "-- query-begin" and "-- query-end" is plain, portable T-SQL: the local check runs it on DuckDB.
-- sqlserver only
IF SCHEMA_ID(N'Rpt') IS NULL EXEC (N'CREATE SCHEMA Rpt');
GO
DROP PROCEDURE IF EXISTS Rpt.usp_Regions;
DROP PROCEDURE IF EXISTS Rpt.usp_SalesByProduct;
GO

-- Dataset "SalesByProduct": units, orders and revenue per product for a date range and one region (or all).
-- Revenue is the line value after the line discount. Cancelled orders are not counted.
CREATE OR ALTER PROCEDURE Rpt.usp_SalesByProduct
    @From   date,
    @To     date,
    @Region nvarchar(20) = N'ALL'
AS
BEGIN
    SET NOCOUNT ON;
    -- query-begin
    SELECT p.ProductName,
           SUM(l.Qty) AS UnitsSold,
           COUNT(DISTINCT o.OrderId) AS Orders,
           CAST(SUM(l.Qty * l.UnitPrice * (1 - l.DiscountPct / 100.0)) AS decimal(12,2)) AS Revenue
    FROM Sales.OrderLines AS l
    JOIN Sales.Orders AS o ON o.OrderId = l.OrderId
    JOIN Sales.Products AS p ON p.ProductId = l.ProductId
    JOIN Sales.Customers AS c ON c.CustomerId = o.CustomerId
    WHERE o.OrderDate BETWEEN @From AND @To
      AND o.Status <> N'Cancelled'
      AND (@Region = N'ALL' OR c.Region = @Region)
    GROUP BY p.ProductName
    ORDER BY Revenue DESC, p.ProductName;
    -- query-end
END
GO

-- Dataset "Regions": the values of the Region parameter's drop-down. 'ALL' is a real value, not NULL, because a
-- drop-down cannot select NULL.
CREATE OR ALTER PROCEDURE Rpt.usp_Regions
AS
BEGIN
    SET NOCOUNT ON;
    -- query-begin
    SELECT RegionCode, RegionName
    FROM (SELECT N'ALL' AS RegionCode, N'(All regions)' AS RegionName
          UNION ALL
          SELECT DISTINCT Region, Region FROM Sales.Customers) AS r
    ORDER BY CASE WHEN RegionCode = N'ALL' THEN 0 ELSE 1 END, RegionName;
    -- query-end
END
GO
