-- 14-sign-search-procedure.sql
-- SQL Server only. Dynamic SQL breaks the ownership chain, so the caller of usp_SearchCustomers would need
-- SELECT on Sales.Customers. Instead we sign the procedure with a certificate and grant SELECT to a user
-- created from that certificate: its permission applies only while the signed procedure runs, and the caller
-- stays the caller (row-level security still sees sales_north, not a proxy user).
-- The certificate's private key is protected by a throwaway password generated here and never stored; after
-- signing, the private key is removed, so nobody can sign anything else with it. Re-runnable.

IF EXISTS (SELECT 1
           FROM sys.crypt_properties AS cp
           JOIN sys.certificates AS c ON c.thumbprint = cp.thumbprint
           WHERE cp.major_id = OBJECT_ID(N'Sales.usp_SearchCustomers') AND c.name = N'SearchSigningCert')
    DROP SIGNATURE FROM Sales.usp_SearchCustomers BY CERTIFICATE SearchSigningCert;
DROP USER IF EXISTS search_signer;
IF CERT_ID(N'SearchSigningCert') IS NOT NULL
    DROP CERTIFICATE SearchSigningCert;
GO

DECLARE @pw nvarchar(64) = CONVERT(nvarchar(36), NEWID()) + N'aA1!';
DECLARE @sql nvarchar(max) =
      N'CREATE CERTIFICATE SearchSigningCert ENCRYPTION BY PASSWORD = ' + QUOTENAME(@pw, N'''')
    + N' WITH SUBJECT = N''Signs Sales.usp_SearchCustomers'', EXPIRY_DATE = ''20301231'';'
    + N' ADD SIGNATURE TO Sales.usp_SearchCustomers BY CERTIFICATE SearchSigningCert WITH PASSWORD = '
    + QUOTENAME(@pw, N'''') + N';';
EXEC sys.sp_executesql @sql;
GO

ALTER CERTIFICATE SearchSigningCert REMOVE PRIVATE KEY;
GO

CREATE USER search_signer FROM CERTIFICATE SearchSigningCert;
GRANT SELECT ON OBJECT::Sales.Customers TO search_signer;
GO
