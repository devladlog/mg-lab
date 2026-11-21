-- Lab only (CON-SQL01, SQL Server 2022 Developer). Fictional Contoso Bikes data.
IF DB_ID(N'contoso_pricing') IS NULL CREATE DATABASE contoso_pricing;
GO
USE contoso_pricing;
GO
IF OBJECT_ID(N'dbo.PriceList') IS NULL
    CREATE TABLE dbo.PriceList (Sku nvarchar(40) NOT NULL PRIMARY KEY, ListPrice decimal(10,2) NOT NULL);
GO
MERGE dbo.PriceList AS t
USING (VALUES (N'BIKE-100', 1299.00), (N'BIKE-200', 2499.00), (N'HELMET-01', 89.90)) AS s(Sku, ListPrice)
ON t.Sku = s.Sku
WHEN MATCHED THEN UPDATE SET ListPrice = s.ListPrice
WHEN NOT MATCHED THEN INSERT (Sku, ListPrice) VALUES (s.Sku, s.ListPrice);
GO
-- The password is typed at the console, never stored in a file:
-- CREATE LOGIN pricing_app WITH PASSWORD = N'<typed at the console>';  CREATE USER pricing_app FOR LOGIN pricing_app;
-- ALTER ROLE db_datareader ADD MEMBER pricing_app;
GO
