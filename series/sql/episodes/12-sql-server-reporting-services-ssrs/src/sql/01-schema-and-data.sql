-- 01-schema-and-data.sql
-- Fictional Contoso Bikes order system: customers, products with stock, orders and order lines.
-- Run it in ContosoBikesApp. Re-runnable: drops and recreates the tables and the order number sequence.
-- Seed orders use OrderId 1001-1008; orders placed by the procedures get numbers from 2001 (the sequence).
-- Batches marked "sqlserver only" are skipped by the local DuckDB check.

-- sqlserver only
IF SCHEMA_ID(N'Sales') IS NULL
    EXEC (N'CREATE SCHEMA Sales');
GO

DROP TABLE IF EXISTS Sales.OrderLines;
DROP TABLE IF EXISTS Sales.Orders;
DROP TABLE IF EXISTS Sales.Products;
DROP TABLE IF EXISTS Sales.Customers;
DROP SEQUENCE IF EXISTS Sales.OrderNumbers;
GO

CREATE SEQUENCE Sales.OrderNumbers START WITH 2001 INCREMENT BY 1;

CREATE TABLE Sales.Customers (
    CustomerId   int           NOT NULL CONSTRAINT PK_Customers PRIMARY KEY,
    CustomerName nvarchar(100) NOT NULL,
    Email        nvarchar(254) NOT NULL CONSTRAINT UQ_Customers_Email UNIQUE,
    Region       nvarchar(20)  NOT NULL CONSTRAINT CK_Customers_Region CHECK (Region IN (N'North', N'Centre', N'South'))
);

CREATE TABLE Sales.Products (
    ProductId   int           NOT NULL CONSTRAINT PK_Products PRIMARY KEY,
    ProductName nvarchar(100) NOT NULL,
    ListPrice   decimal(10,2) NOT NULL CONSTRAINT CK_Products_ListPrice CHECK (ListPrice >= 0),
    StockQty    int           NOT NULL CONSTRAINT CK_Products_StockQty CHECK (StockQty >= 0)
);

CREATE TABLE Sales.Orders (
    OrderId    int          NOT NULL CONSTRAINT PK_Orders PRIMARY KEY,
    CustomerId int          NOT NULL CONSTRAINT FK_Orders_Customers REFERENCES Sales.Customers (CustomerId),
    OrderDate  date         NOT NULL,
    Status     nvarchar(20) NOT NULL CONSTRAINT CK_Orders_Status CHECK (Status IN (N'Placed', N'Shipped', N'Cancelled'))
);

CREATE TABLE Sales.OrderLines (
    OrderId     int           NOT NULL CONSTRAINT FK_OrderLines_Orders REFERENCES Sales.Orders (OrderId),
    LineNumber  int           NOT NULL,
    ProductId   int           NOT NULL CONSTRAINT FK_OrderLines_Products REFERENCES Sales.Products (ProductId),
    Qty         int           NOT NULL CONSTRAINT CK_OrderLines_Qty CHECK (Qty > 0),
    UnitPrice   decimal(10,2) NOT NULL,
    DiscountPct decimal(5,2)  NOT NULL CONSTRAINT CK_OrderLines_DiscountPct CHECK (DiscountPct BETWEEN 0 AND 100),
    CONSTRAINT PK_OrderLines PRIMARY KEY (OrderId, LineNumber)
);
GO

INSERT INTO Sales.Customers (CustomerId, CustomerName, Email, Region) VALUES
    (1, N'Alex Demo',         N'alex.demo@contoso.com',         N'North'),
    (2, N'Rita Sample',       N'rita.sample@contoso.com',       N'North'),
    (3, N'Bruno Test',        N'bruno.test@contoso.com',        N'Centre'),
    (4, N'Carla Example',     N'carla.example@contoso.com',     N'Centre'),
    (5, N'Diego Placeholder', N'diego.placeholder@contoso.com', N'South'),
    (6, N'Eva Newcustomer',   N'eva.newcustomer@contoso.com',   N'South');   -- no orders yet

INSERT INTO Sales.Products (ProductId, ProductName, ListPrice, StockQty) VALUES
    (1, N'Trail Helmet',     89.90,  40),
    (2, N'City Bike',       649.00,   6),
    (3, N'Bike Lock',        24.50, 120),
    (4, N'Carbon Wheelset', 1199.00,  2),   -- only two in stock: the out-of-stock demo asks for three
    (5, N'LED Light Set',    39.95,  75);

INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES
    (1001, 1, '2025-03-03', N'Shipped'),
    (1002, 3, '2025-03-05', N'Shipped'),
    (1003, 2, '2025-03-12', N'Shipped'),
    (1004, 5, '2025-03-18', N'Shipped'),
    (1005, 1, '2025-04-02', N'Shipped'),
    (1006, 4, '2025-04-09', N'Placed'),
    (1007, 3, '2025-04-15', N'Placed'),
    (1008, 5, '2025-04-22', N'Placed');

INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct) VALUES
    (1001, 1, 2, 1,  649.00,  0.00),
    (1001, 2, 1, 1,   89.90, 10.00),
    (1001, 3, 3, 2,   24.50,  0.00),
    (1002, 1, 5, 3,   39.95,  0.00),
    (1003, 1, 2, 2,  649.00,  5.00),
    (1003, 2, 1, 2,   89.90,  5.00),
    (1004, 1, 4, 1, 1199.00, 15.00),
    (1005, 1, 3, 4,   24.50,  0.00),
    (1005, 2, 5, 1,   39.95,  0.00),
    (1006, 1, 1, 3,   89.90,  0.00),
    (1007, 1, 2, 1,  649.00,  0.00),
    (1007, 2, 5, 2,   39.95, 10.00),
    (1008, 1, 3, 1,   24.50,  0.00);
GO
