-- 12-principals-and-grants.sql
-- SQL Server only. Database users without logins (the lab impersonates them with EXECUTE AS USER), roles,
-- and grants to roles, on procedures, never on tables.

CREATE ROLE app_sales;      -- the order application
CREATE ROLE reporting;      -- ad hoc reporting
GO
CREATE USER sales_north WITHOUT LOGIN;
CREATE USER sales_south WITHOUT LOGIN;
CREATE USER analyst_demo WITHOUT LOGIN;
ALTER ROLE app_sales ADD MEMBER sales_north;
ALTER ROLE app_sales ADD MEMBER sales_south;
ALTER ROLE reporting ADD MEMBER analyst_demo;
GO

GRANT EXECUTE ON OBJECT::Sales.usp_PlaceOrder      TO app_sales;
GRANT EXECUTE ON OBJECT::Sales.usp_ListCustomers   TO app_sales;
GRANT EXECUTE ON OBJECT::Sales.usp_SearchCustomers TO app_sales;
-- A table-valued parameter needs EXECUTE and REFERENCES on its table type.
GRANT EXECUTE, REFERENCES ON TYPE::Sales.OrderLineList TO app_sales;

GRANT SELECT ON SCHEMA::Sales TO reporting;
GO
