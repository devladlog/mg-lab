-- Run in database contoso_analytics. sqlcmd variable: StorageAccount (name only, for example stlakexyz).
-- Entra passthrough: no credential. The user running a query needs Storage Blob Data Reader on the account.
IF NOT EXISTS (SELECT 1 FROM sys.external_data_sources WHERE name = N'lake')
    CREATE EXTERNAL DATA SOURCE lake WITH (LOCATION = 'https://$(StorageAccount).dfs.core.windows.net/lake');
GO
IF SCHEMA_ID(N'bronze')  IS NULL EXEC (N'CREATE SCHEMA bronze');
GO
IF SCHEMA_ID(N'silver')  IS NULL EXEC (N'CREATE SCHEMA silver');
GO
IF SCHEMA_ID(N'gold')    IS NULL EXEC (N'CREATE SCHEMA gold');
GO
IF SCHEMA_ID(N'ref')     IS NULL EXEC (N'CREATE SCHEMA ref');
GO
IF SCHEMA_ID(N'quality') IS NULL EXEC (N'CREATE SCHEMA quality');
GO
