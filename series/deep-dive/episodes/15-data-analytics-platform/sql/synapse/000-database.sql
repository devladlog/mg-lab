-- Run against the serverless endpoint, database master, as a Synapse Administrator (or SQL administrator).
-- Learn: string columns in Parquet are UTF-8, so use a UTF-8 database collation (also enables Parquet row-group elimination).
IF DB_ID(N'contoso_analytics') IS NULL
    CREATE DATABASE contoso_analytics COLLATE Latin1_General_100_BIN2_UTF8;
GO
