-- 01-contoso-copilot.sql
-- Fictional Contoso sales data for the Copilot for SQL episode. SQL Server 2022 (CON-SQL01) or Azure SQL Database.
-- Run it in an EMPTY database that you created for the demo (sqlcmd -d ContosoCopilot -i 01-contoso-copilot.sql).
-- Re-runnable: drops and recreates its own objects. Keys are explicit (no IDENTITY) so every result in expected/
-- is deterministic. Cancelled orders do not count as revenue (the constitution says so).

DROP VIEW IF EXISTS Reporting.MonthlyRevenue;
DROP TABLE IF EXISTS Sales.OrderLines;
DROP TABLE IF EXISTS Sales.Orders;
DROP TABLE IF EXISTS Sales.Products;
DROP TABLE IF EXISTS Sales.Customers;
GO
DROP SCHEMA IF EXISTS Reporting;
DROP SCHEMA IF EXISTS Sales;
GO
CREATE SCHEMA Sales;
GO
CREATE SCHEMA Reporting;
GO

CREATE TABLE Sales.Customers (
    CustomerId   int           NOT NULL CONSTRAINT PK_Customers PRIMARY KEY,
    CustomerName nvarchar(100) NOT NULL,
    Region       nvarchar(20)  NOT NULL,
    Email        nvarchar(100) NOT NULL
);

CREATE TABLE Sales.Products (
    ProductId   int           NOT NULL CONSTRAINT PK_Products PRIMARY KEY,
    ProductName nvarchar(100) NOT NULL,
    Category    nvarchar(30)  NOT NULL,
    ListPrice   decimal(10,2) NOT NULL
);

CREATE TABLE Sales.Orders (
    OrderId    int          NOT NULL CONSTRAINT PK_Orders PRIMARY KEY,
    CustomerId int          NOT NULL CONSTRAINT FK_Orders_Customers REFERENCES Sales.Customers (CustomerId),
    OrderDate  date         NOT NULL,
    Status     nvarchar(12) NOT NULL CONSTRAINT CK_Orders_Status CHECK (Status IN (N'Pending', N'Shipped', N'Cancelled'))
);

CREATE TABLE Sales.OrderLines (
    OrderLineId int           NOT NULL CONSTRAINT PK_OrderLines PRIMARY KEY,
    OrderId     int           NOT NULL CONSTRAINT FK_OrderLines_Orders   REFERENCES Sales.Orders (OrderId),
    ProductId   int           NOT NULL CONSTRAINT FK_OrderLines_Products REFERENCES Sales.Products (ProductId),
    Quantity    int           NOT NULL CONSTRAINT CK_OrderLines_Quantity CHECK (Quantity > 0),
    UnitPrice   decimal(10,2) NOT NULL
);
GO

INSERT INTO Sales.Customers (CustomerId, CustomerName, Region, Email) VALUES
    (1, N'Alex Demo', N'North', N'alex.demo@example.com'),
    (2, N'Rita Sample', N'North', N'rita.sample@example.com'),
    (3, N'Bruno Test', N'Centre', N'bruno.test@example.com'),
    (4, N'Carla Example', N'Centre', N'carla.example@example.com'),
    (5, N'Diego Placeholder', N'South', N'diego.placeholder@example.com'),
    (6, N'Eva Newcustomer', N'South', N'eva.newcustomer@example.com'),
    (7, N'Filipe Fictional', N'North', N'filipe.fictional@example.com'),
    (8, N'Graca Mockup', N'Centre', N'graca.mockup@example.com'),
    (9, N'Hugo Dummy', N'South', N'hugo.dummy@example.com'),
    (10, N'Ines Foobar', N'North', N'ines.foobar@example.com');  -- customer 6 has no orders

INSERT INTO Sales.Products (ProductId, ProductName, Category, ListPrice) VALUES
    (1, N'Trail Bike 29', N'Bikes', 1450.00),
    (2, N'City Bike 28', N'Bikes', 690.00),
    (3, N'Road Helmet', N'Helmets', 89.90),
    (4, N'Kids Helmet', N'Helmets', 39.90),
    (5, N'Bike Lock', N'Accessories', 24.50),
    (6, N'LED Light Set', N'Accessories', 32.00),
    (7, N'Pannier Bag', N'Accessories', 58.00),
    (8, N'Floor Pump', N'Accessories', 27.50);

INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1, 5, '2026-07-03', N'Shipped'),
    (2, 4, '2026-07-09', N'Cancelled'),
    (3, 3, '2026-07-11', N'Shipped'),
    (4, 8, '2026-07-16', N'Shipped'),
    (5, 9, '2026-07-19', N'Shipped'),
    (6, 9, '2026-07-24', N'Cancelled'),
    (7, 10, '2026-07-28', N'Shipped'),
    (8, 10, '2026-08-02', N'Shipped'),
    (9, 2, '2026-08-06', N'Shipped'),
    (10, 3, '2026-08-08', N'Pending'),
    (11, 5, '2026-08-13', N'Cancelled'),
    (12, 4, '2026-08-17', N'Shipped'),
    (13, 7, '2026-08-22', N'Pending'),
    (14, 8, '2026-08-25', N'Pending'),
    (15, 2, '2026-08-29', N'Cancelled'),
    (16, 4, '2026-09-02', N'Shipped'),
    (17, 2, '2026-09-06', N'Shipped'),
    (18, 8, '2026-09-09', N'Shipped'),
    (19, 9, '2026-09-14', N'Shipped'),
    (20, 2, '2026-09-18', N'Cancelled'),
    (21, 4, '2026-09-21', N'Cancelled'),
    (22, 7, '2026-09-25', N'Shipped'),
    (23, 8, '2026-09-30', N'Shipped'),
    (24, 1, '2026-10-05', N'Pending'),
    (25, 4, '2026-10-07', N'Cancelled'),
    (26, 7, '2026-10-13', N'Cancelled'),
    (27, 8, '2026-10-17', N'Shipped'),
    (28, 7, '2026-10-19', N'Pending'),
    (29, 4, '2026-10-25', N'Cancelled'),
    (30, 7, '2026-10-27', N'Shipped');

INSERT INTO Sales.OrderLines (OrderLineId, OrderId, ProductId, Quantity, UnitPrice) VALUES
    (1, 1, 3, 4, 89.90),
    (2, 1, 1, 1, 1450.00),
    (3, 2, 3, 4, 89.90),
    (4, 2, 1, 2, 1450.00),
    (5, 2, 7, 4, 58.00),
    (6, 3, 1, 3, 1450.00),
    (7, 3, 7, 2, 58.00),
    (8, 4, 1, 1, 1450.00),
    (9, 5, 3, 6, 89.90),
    (10, 6, 5, 2, 24.50),
    (11, 6, 3, 2, 89.90),
    (12, 6, 1, 1, 1450.00),
    (13, 7, 3, 6, 89.90),
    (14, 8, 5, 4, 24.50),
    (15, 8, 3, 2, 89.90),
    (16, 9, 5, 4, 24.50),
    (17, 10, 7, 4, 58.00),
    (18, 10, 5, 6, 24.50),
    (19, 10, 3, 6, 89.90),
    (20, 11, 5, 6, 24.50),
    (21, 11, 3, 2, 89.90),
    (22, 12, 5, 2, 24.50),
    (23, 13, 7, 2, 58.00),
    (24, 13, 5, 6, 24.50),
    (25, 14, 7, 6, 58.00),
    (26, 14, 5, 6, 24.50),
    (27, 14, 3, 4, 89.90),
    (28, 15, 5, 4, 24.50),
    (29, 16, 7, 4, 58.00),
    (30, 16, 5, 6, 24.50),
    (31, 17, 7, 4, 58.00),
    (32, 18, 1, 3, 1450.00),
    (33, 18, 7, 2, 58.00),
    (34, 19, 1, 3, 1450.00),
    (35, 19, 7, 4, 58.00),
    (36, 20, 1, 3, 1450.00),
    (37, 20, 7, 4, 58.00),
    (38, 21, 1, 3, 1450.00),
    (39, 21, 7, 6, 58.00),
    (40, 21, 5, 4, 24.50),
    (41, 22, 7, 6, 58.00),
    (42, 23, 1, 1, 1450.00),
    (43, 24, 3, 6, 89.90),
    (44, 24, 1, 2, 1450.00),
    (45, 25, 3, 6, 89.90),
    (46, 25, 1, 1, 1450.00),
    (47, 25, 7, 4, 58.00),
    (48, 26, 1, 2, 1450.00),
    (49, 26, 7, 6, 58.00),
    (50, 26, 5, 4, 24.50),
    (51, 27, 7, 2, 58.00),
    (52, 27, 5, 6, 24.50),
    (53, 28, 7, 4, 58.00),
    (54, 28, 5, 4, 24.50),
    (55, 29, 7, 6, 58.00),
    (56, 29, 5, 2, 24.50),
    (57, 30, 7, 4, 58.00),
    (58, 30, 5, 2, 24.50);
GO

-- Revenue per month and product category, cancelled orders excluded.
CREATE VIEW Reporting.MonthlyRevenue
AS
SELECT DATEFROMPARTS(YEAR(o.OrderDate), MONTH(o.OrderDate), 1) AS MonthStart,
       p.Category,
       SUM(l.Quantity * l.UnitPrice)                           AS Revenue
FROM Sales.Orders AS o
JOIN Sales.OrderLines AS l ON l.OrderId = o.OrderId
JOIN Sales.Products   AS p ON p.ProductId = l.ProductId
WHERE o.Status <> N'Cancelled'
GROUP BY DATEFROMPARTS(YEAR(o.OrderDate), MONTH(o.OrderDate), 1), p.Category;
GO
