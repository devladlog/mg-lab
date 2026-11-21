-- 10-reset-security.sql
-- SQL Server only. Removes everything this episode creates, in dependency order, so the lab is repeatable
-- and episode 5's 01-schema-and-data.sql can drop and recreate the tables (a schema-bound security policy
-- would block that). Safe to run when nothing exists yet. Also the tear-down script.

DROP SECURITY POLICY IF EXISTS Security.RegionPolicy;
DROP FUNCTION IF EXISTS Security.fn_CustomerRegionPredicate;
DROP FUNCTION IF EXISTS Security.fn_OrderCustomerPredicate;
DROP TABLE IF EXISTS Security.UserRegion;
GO

DROP PROCEDURE IF EXISTS Sales.usp_ListCustomers;
DROP PROCEDURE IF EXISTS Sales.usp_SearchCustomers;          -- dropping the procedure drops its signature
DROP PROCEDURE IF EXISTS Sales.usp_SearchCustomers_Unsafe;
DROP USER IF EXISTS search_signer;
IF CERT_ID(N'SearchSigningCert') IS NOT NULL
    DROP CERTIFICATE SearchSigningCert;
GO

DROP USER IF EXISTS sales_north;
DROP USER IF EXISTS sales_south;
DROP USER IF EXISTS analyst_demo;
DROP ROLE IF EXISTS app_sales;
DROP ROLE IF EXISTS reporting;
GO

-- The mask (see 13-dynamic-data-masking.sql for why the UNIQUE constraint is dropped and re-created around it).
-- Dynamic SQL: the ALTER statements are only compiled when the column really is masked.
IF EXISTS (SELECT 1 FROM sys.masked_columns WHERE object_id = OBJECT_ID(N'Sales.Customers') AND name = N'Email')
BEGIN
    EXEC (N'ALTER TABLE Sales.Customers DROP CONSTRAINT UQ_Customers_Email;');
    EXEC (N'ALTER TABLE Sales.Customers ALTER COLUMN Email DROP MASKED;');
    EXEC (N'ALTER TABLE Sales.Customers ADD CONSTRAINT UQ_Customers_Email UNIQUE (Email);');
END;
GO
