-- 01-schema-and-data.sql
-- Fictional Contoso Bikes data for the T-SQL Advanced Queries episode.
-- Run it in the ContosoLab database (sqlcmd -d ContosoLab -i ...). Re-runnable: drops and recreates everything.
-- Keys are explicit (no IDENTITY) so every result in expected/ is deterministic.

DROP TABLE IF EXISTS Sales.Orders;
DROP TABLE IF EXISTS Sales.Customers;
DROP TABLE IF EXISTS HR.Employees;
DROP TABLE IF EXISTS App.Logins;
GO
DROP SCHEMA IF EXISTS Sales;
DROP SCHEMA IF EXISTS HR;
DROP SCHEMA IF EXISTS App;
GO
CREATE SCHEMA Sales;
GO
CREATE SCHEMA HR;
GO
CREATE SCHEMA App;
GO

CREATE TABLE Sales.Customers (
    CustomerId   int           NOT NULL CONSTRAINT PK_Customers PRIMARY KEY,
    CustomerName nvarchar(100) NOT NULL,
    Region       nvarchar(20)  NOT NULL
);

CREATE TABLE Sales.Orders (
    OrderId     int           NOT NULL CONSTRAINT PK_Orders PRIMARY KEY,
    CustomerId  int           NOT NULL CONSTRAINT FK_Orders_Customers REFERENCES Sales.Customers (CustomerId),
    OrderDate   date          NOT NULL,
    TotalAmount decimal(10,2) NOT NULL CONSTRAINT CK_Orders_TotalAmount CHECK (TotalAmount >= 0)
);

CREATE TABLE HR.Employees (
    EmployeeId int           NOT NULL CONSTRAINT PK_Employees PRIMARY KEY,
    FullName   nvarchar(100) NOT NULL,
    JobTitle   nvarchar(100) NOT NULL,
    ManagerId  int           NULL CONSTRAINT FK_Employees_Manager REFERENCES HR.Employees (EmployeeId)
);

CREATE TABLE App.Logins (
    LoginId  int           NOT NULL CONSTRAINT PK_Logins PRIMARY KEY,
    UserName nvarchar(50)  NOT NULL,
    LoginAt  datetime2(0)  NOT NULL
);
GO

INSERT INTO Sales.Customers (CustomerId, CustomerName, Region) VALUES
    (1, N'Alex Demo',        N'North'),
    (2, N'Rita Sample',      N'North'),
    (3, N'Bruno Test',       N'Centre'),
    (4, N'Carla Example',    N'Centre'),
    (5, N'Diego Placeholder', N'South'),
    (6, N'Eva Newcustomer',  N'South');   -- no orders yet (CROSS vs OUTER APPLY)

INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, TotalAmount) VALUES
    ( 1, 1, '2025-01-08', 1250.00),
    ( 2, 3, '2025-01-15',  480.50),
    ( 3, 2, '2025-01-15', 2300.00),   -- same day as order 2 (the RANGE gotcha)
    ( 4, 5, '2025-01-29',  799.90),
    ( 5, 1, '2025-02-03',  340.00),
    ( 6, 4, '2025-02-11', 1890.00),
    ( 7, 3, '2025-02-11',  260.00),
    ( 8, 2, '2025-02-20', 1100.00),
    ( 9, 5, '2025-03-04', 2450.00),
    (10, 1, '2025-03-12', 2300.00),
    (11, 4, '2025-03-12',  615.25),
    (12, 3, '2025-03-27',  990.00),
    (13, 2, '2025-04-02',  410.00),
    (14, 1, '2025-04-16', 1250.00),   -- same amount as order 1: top-N needs a tie-breaker
    (15, 5, '2025-04-16',  380.00),
    (16, 4, '2025-05-05', 2750.00),
    (17, 3, '2025-05-19', 1420.00),
    (18, 2, '2025-05-19',  860.00),
    (19, 5, '2025-06-02', 1675.50),
    (20, 1, '2025-06-10',  520.00),
    (21, 4, '2025-06-24',  330.00);

-- One INSERT per level: SQL Server checks the self-referencing foreign key per statement,
-- DuckDB (the local harness) per row, so managers go in before their reports.
INSERT INTO HR.Employees (EmployeeId, FullName, JobTitle, ManagerId) VALUES
    (1, N'Sofia Lead',  N'Managing Director',   NULL);
INSERT INTO HR.Employees (EmployeeId, FullName, JobTitle, ManagerId) VALUES
    (2, N'Tiago North', N'Sales Director',      1),
    (3, N'Ines Ops',    N'Operations Director', 1);
INSERT INTO HR.Employees (EmployeeId, FullName, JobTitle, ManagerId) VALUES
    (4, N'Joao Field',  N'Account Manager',     2),
    (5, N'Marta Field', N'Account Manager',     2),
    (6, N'Nuno Ware',   N'Warehouse Lead',      3);
INSERT INTO HR.Employees (EmployeeId, FullName, JobTitle, ManagerId) VALUES
    (7, N'Paula Pick',  N'Picker',              6),
    (8, N'Rui Pack',    N'Packer',              6),
    (9, N'Lara Intern', N'Sales Intern',        4);

INSERT INTO App.Logins (LoginId, UserName, LoginAt) VALUES
    ( 1, N'alex.demo',   '2025-03-01 09:00:00'),
    ( 2, N'alex.demo',   '2025-03-01 17:30:00'),   -- second login on the same day
    ( 3, N'alex.demo',   '2025-03-02 08:45:00'),
    ( 4, N'alex.demo',   '2025-03-03 10:15:00'),
    ( 5, N'alex.demo',   '2025-03-05 09:05:00'),
    ( 6, N'alex.demo',   '2025-03-06 11:20:00'),
    ( 7, N'alex.demo',   '2025-03-09 14:00:00'),
    ( 8, N'rita.sample', '2025-03-02 08:00:00'),
    ( 9, N'rita.sample', '2025-03-03 08:10:00'),
    (10, N'rita.sample', '2025-03-04 08:05:00'),
    (11, N'rita.sample', '2025-03-05 07:55:00'),
    (12, N'rita.sample', '2025-03-08 12:00:00'),
    (13, N'rita.sample', '2025-03-10 09:30:00'),
    (14, N'rita.sample', '2025-03-11 09:40:00');
GO
