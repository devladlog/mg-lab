-- a03-endpoint-sql01.sql
-- SQL Server only. Run on CON-SQL01. The database mirroring endpoint the replicas talk to (one per instance), Windows
-- authentication, AES encryption, port 5022. The peer's service connects as its computer account (CONTOSO\CON-SQL02$)
-- when SQL Server runs as a virtual account or Network Service, so that account needs a login and CONNECT on the
-- endpoint. Check the real service accounts first (sys.dm_server_services, demo.md) and change the login name here if
-- the services run under a domain account. The endpoint is created only if it does not exist yet (re-runnable).
USE master;
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_mirroring_endpoints WHERE name = N'Hadr_endpoint')
    CREATE ENDPOINT Hadr_endpoint
        STATE = STARTED
        AS TCP (LISTENER_PORT = 5022)
        FOR DATABASE_MIRRORING (ROLE = ALL, AUTHENTICATION = WINDOWS NEGOTIATE, ENCRYPTION = REQUIRED ALGORITHM AES);
GO
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'CONTOSO\CON-SQL02$')
    CREATE LOGIN [CONTOSO\CON-SQL02$] FROM WINDOWS;
GO
GRANT CONNECT ON ENDPOINT::Hadr_endpoint TO [CONTOSO\CON-SQL02$];
GO
SELECT CONVERT(nvarchar(60), SERVERPROPERTY(N'ServerName')) AS Node,
       e.name AS Endpoint, e.state_desc AS State, e.role_desc AS Role,
       e.connection_auth_desc AS Auth, e.encryption_algorithm_desc AS Encryption
FROM sys.database_mirroring_endpoints AS e;
GO
