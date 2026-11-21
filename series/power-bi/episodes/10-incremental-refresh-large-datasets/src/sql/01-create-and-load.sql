-- ContosoBikesIR: a fictional order-line table for the incremental refresh episode (Azure SQL Database, free offer).
-- Deterministic: row n always gets the same values, so tools/sql_mirror.py can compute the expected totals without a server.
-- Four years of order lines (2023-01-01 .. 2026-12-31), five lines per order. Change @Rows to scale it.
SET NOCOUNT ON;
GO
DROP TABLE IF EXISTS dbo.Sales;
GO
CREATE TABLE dbo.Sales (
    SalesId        bigint        NOT NULL,
    OrderNumber    char(10)      NOT NULL,
    LineNumber     int           NOT NULL,
    OrderTimestamp datetime2(0)  NOT NULL,
    ModifiedDate   datetime2(0)  NOT NULL,
    StoreName      varchar(30)   NOT NULL,
    Channel        varchar(10)   NOT NULL,
    Category       varchar(20)   NOT NULL,
    Quantity       int           NOT NULL,
    UnitPrice      decimal(10,2) NOT NULL,
    YearMonth      AS CONVERT(char(7), OrderTimestamp, 23) PERSISTED,
    CONSTRAINT PK_Sales PRIMARY KEY NONCLUSTERED (SalesId)
);
-- The model filters on OrderTimestamp with >= and <, so a clustered index on it turns every partition query into a range scan.
CREATE CLUSTERED INDEX CIX_Sales_OrderTimestamp ON dbo.Sales (OrderTimestamp, SalesId);
GO
DECLARE @Rows bigint = 2000000;

WITH nums AS (
    SELECT TOP (@Rows) CAST(ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS bigint) AS n
    FROM sys.all_objects AS a CROSS JOIN sys.all_objects AS b CROSS JOIN sys.all_objects AS c
), orders AS (
    SELECT n, (n - 1) / 5 AS o FROM nums
), stamped AS (
    SELECT n, o,
           DATEADD(second, (o * 104729) % 86400, DATEADD(day, (o * 7919) % 1461, CAST('2023-01-01T00:00:00' AS datetime2(0)))) AS ts,
           (o * 31) % 5 AS store
    FROM orders
)
INSERT INTO dbo.Sales (SalesId, OrderNumber, LineNumber, OrderTimestamp, ModifiedDate, StoreName, Channel, Category, Quantity, UnitPrice)
SELECT n,
       'SO-' + RIGHT('0000000' + CAST(o + 1 AS varchar(10)), 7),
       CAST((n - 1) % 5 + 1 AS int),
       ts,
       DATEADD(minute, (o * 37) % 600, ts),
       CHOOSE(store + 1, 'Contoso Madrid', 'Contoso Lisboa', 'Contoso Paris', 'Contoso Porto', 'Contoso Online'),
       CASE WHEN store = 4 THEN 'Online' ELSE 'Store' END,
       CHOOSE((n * 17) % 3 + 1, 'Bikes', 'Clothing', 'Accessories'),
       CAST(1 + (n * 13) % 5 AS int),
       CAST((2000 + (n * 7919) % 98000) / 100.0 AS decimal(10,2))
FROM stamped;
GO
