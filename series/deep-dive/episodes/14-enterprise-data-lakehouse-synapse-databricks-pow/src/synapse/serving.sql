-- Synapse serverless SQL pool: serving views over the gold Delta tables.
-- Run in a user database (not master). Delta is read-only here: serverless cannot write Delta.
-- Reader limits to respect (Microsoft Learn, serverless SQL pool self-help): Delta reader v1, so no deletion
-- vectors, no column mapping/renames, no time travel. The lakehouse writes gold with deletion vectors off.
ALTER DATABASE CURRENT COLLATE Latin1_General_100_BIN2_UTF8;
GO

IF SCHEMA_ID('gold') IS NULL EXEC('CREATE SCHEMA gold');
GO

-- No credential: the caller's Microsoft Entra identity needs Storage Blob Data Reader on the lake.
IF NOT EXISTS (SELECT 1 FROM sys.external_data_sources WHERE name = 'lake')
    CREATE EXTERNAL DATA SOURCE lake WITH (LOCATION = 'https://<storage-account>.dfs.core.windows.net/lake');
GO

CREATE OR ALTER VIEW gold.daily_sales AS
SELECT r.order_date, r.region, r.currency, r.orders, r.revenue
FROM OPENROWSET(BULK 'gold/daily_sales', DATA_SOURCE = 'lake', FORMAT = 'DELTA')
WITH (
    order_date date,
    region     varchar(16) COLLATE Latin1_General_100_BIN2_UTF8,
    currency   varchar(3)  COLLATE Latin1_General_100_BIN2_UTF8,
    orders     bigint,
    revenue    decimal(22,2)
) AS r;
GO

CREATE OR ALTER VIEW gold.customer_summary AS
SELECT r.customer_key, r.orders, r.revenue, r.first_order_date, r.last_order_date
FROM OPENROWSET(BULK 'gold/customer_summary', DATA_SOURCE = 'lake', FORMAT = 'DELTA')
WITH (
    customer_key     varchar(64) COLLATE Latin1_General_100_BIN2_UTF8,
    orders           bigint,
    revenue          decimal(22,2),
    first_order_date date,
    last_order_date  date
) AS r;
GO
