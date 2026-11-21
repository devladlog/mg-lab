-- 15-row-level-security.sql
-- SQL Server only. Each sales user sees only the customers (and orders) of their regions; db_owner members
-- see everything (Learn: security policies apply to dbo too, so the predicate has to allow it explicitly).

IF SCHEMA_ID(N'Security') IS NULL
    EXEC (N'CREATE SCHEMA Security');
GO

CREATE TABLE Security.UserRegion (
    UserName sysname      NOT NULL,
    Region   nvarchar(20) NOT NULL,
    CONSTRAINT PK_UserRegion PRIMARY KEY (UserName, Region)
);
INSERT INTO Security.UserRegion (UserName, Region) VALUES
    (N'sales_north', N'North'),
    (N'sales_south', N'South'),
    (N'analyst_demo', N'North'), (N'analyst_demo', N'Centre'), (N'analyst_demo', N'South');
GO

CREATE FUNCTION Security.fn_CustomerRegionPredicate (@Region nvarchar(20))
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
    SELECT 1 AS AccessGranted
    WHERE IS_MEMBER(N'db_owner') = 1
       OR EXISTS (SELECT 1 FROM Security.UserRegion AS ur
                  WHERE ur.UserName = USER_NAME() AND ur.Region = @Region);
GO

CREATE FUNCTION Security.fn_OrderCustomerPredicate (@CustomerId int)
RETURNS TABLE
WITH SCHEMABINDING
AS
RETURN
    SELECT 1 AS AccessGranted
    WHERE IS_MEMBER(N'db_owner') = 1
       OR EXISTS (SELECT 1 FROM Sales.Customers AS c
                  JOIN Security.UserRegion AS ur ON ur.Region = c.Region
                  WHERE c.CustomerId = @CustomerId AND ur.UserName = USER_NAME());
GO

CREATE SECURITY POLICY Security.RegionPolicy
    ADD FILTER PREDICATE Security.fn_CustomerRegionPredicate(Region) ON Sales.Customers,
    ADD FILTER PREDICATE Security.fn_OrderCustomerPredicate(CustomerId) ON Sales.Orders
WITH (STATE = ON);
GO
