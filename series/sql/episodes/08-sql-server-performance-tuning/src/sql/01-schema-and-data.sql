-- 01-schema-and-data.sql
-- Contoso Bikes, three years later: 20,000 customers and 200,000 orders (all fictional, all generated).
-- Run it in ContosoBikesPerf (see 00-create-database.sql). Re-runnable: drops and recreates everything.
-- No randomness: every value is integer arithmetic on the row number, so every result in expected/
-- is the same on SQL Server and in the local DuckDB check.
--   * customer 1 (Contoso Megastore) owns 30% of all orders; every other customer has about 7
--   * 1% of orders are Open, dates run from 2023-01-01 to 2026-06-30
--   * Notes makes each row ~400 bytes wide, like a real order row: scanning the table costs real pages
-- The only index is the clustered primary key. The foreign key on CustomerId does NOT create an index.

DROP TABLE IF EXISTS Sales.Orders;
DROP TABLE IF EXISTS Sales.Customers;
GO
DROP SCHEMA IF EXISTS Sales;
GO
CREATE SCHEMA Sales;
GO

CREATE TABLE Sales.Customers (
    CustomerId    int           NOT NULL CONSTRAINT PK_Customers PRIMARY KEY,   -- clustered: the default for a PRIMARY KEY
    AccountNumber varchar(12)   NOT NULL,
    CustomerName  nvarchar(100) NOT NULL,
    Region        nvarchar(20)  NOT NULL
);

CREATE TABLE Sales.Orders (
    OrderId     int           NOT NULL CONSTRAINT PK_Orders PRIMARY KEY,   -- clustered: the default for a PRIMARY KEY
    CustomerId  int           NOT NULL CONSTRAINT FK_Orders_Customers REFERENCES Sales.Customers (CustomerId),
    OrderDate   date          NOT NULL,
    Status      varchar(10)   NOT NULL,
    Channel     varchar(10)   NOT NULL,
    ShipCountry char(2)       NOT NULL,
    TotalAmount decimal(10,2) NOT NULL,
    Notes       nvarchar(200) NOT NULL
);
GO

INSERT INTO Sales.Customers (CustomerId, AccountNumber, CustomerName, Region)
SELECT s.value,
       CAST(100000 + s.value AS varchar(12)),
       CASE WHEN s.value = 1 THEN N'Contoso Megastore' ELSE CONCAT(N'Customer ', s.value) END,
       CASE s.value % 4 WHEN 0 THEN N'North' WHEN 1 THEN N'Centre' WHEN 2 THEN N'South' ELSE N'Islands' END
FROM GENERATE_SERIES(1, 20000) AS s;
GO

INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status, Channel, ShipCountry, TotalAmount, Notes)
SELECT s.value,
       CASE WHEN s.value % 10 < 3 THEN 1 ELSE 2 + (s.value * 7919) % 19999 END,
       DATEADD(day, (s.value * 13) % 1277, CAST('2023-01-01' AS date)),
       CASE WHEN s.value % 100 = 7 THEN 'Open' WHEN s.value % 100 IN (3, 53) THEN 'Cancelled' ELSE 'Shipped' END,
       CASE s.value % 3 WHEN 0 THEN 'Web' WHEN 1 THEN 'Store' ELSE 'Partner' END,
       CASE s.value % 4 WHEN 0 THEN 'PT' WHEN 1 THEN 'ES' WHEN 2 THEN 'FR' ELSE 'DE' END,
       CAST(5 + ((s.value * 37) % 50000) * 0.01 AS decimal(10,2)),
       CONCAT(N'Delivery window: business hours. Gift wrap: no. Reference ', s.value, N'. ', REPLICATE(N'-', 120))
FROM GENERATE_SERIES(1, 200000) AS s;
GO
