-- 00-create-database.sql
-- SQL Server only (the local DuckDB harness skips it). Run against master.
IF DB_ID(N'ContosoTraining') IS NULL
    CREATE DATABASE ContosoTraining;
GO
