-- Contoso purchase requests: the operational source for the analytics platform (Azure SQL Database, free offer).
-- Run as the Microsoft Entra admin of the server. Idempotent. sqlcmd variable: AdfName (the Data Factory name,
-- the managed identity's display name), for example: sqlcmd -S <server> -d <db> -G -v AdfName=adf-analytics-xyz -i this.sql
IF SCHEMA_ID(N'etl') IS NULL EXEC (N'CREATE SCHEMA etl');
GO

IF OBJECT_ID(N'dbo.PurchaseRequests', N'U') IS NULL
CREATE TABLE dbo.PurchaseRequests (
    RequestId      int            NOT NULL CONSTRAINT PK_PurchaseRequests PRIMARY KEY,
    DepartmentCode varchar(10)    NOT NULL,
    Category       nvarchar(40)   NOT NULL,
    VendorName     nvarchar(100)  NOT NULL,
    Amount         decimal(18, 2) NOT NULL,
    Currency       char(3)        NOT NULL,
    Status         varchar(20)    NOT NULL,
    SubmittedOn    datetime2(0)   NOT NULL,
    ApprovedOn     datetime2(0)   NULL,
    ModifiedOn     datetime2(0)   NOT NULL   -- the watermark column: must rise on every insert AND update
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_PurchaseRequests_ModifiedOn' AND object_id = OBJECT_ID(N'dbo.PurchaseRequests'))
CREATE INDEX IX_PurchaseRequests_ModifiedOn ON dbo.PurchaseRequests (ModifiedOn);
GO

-- One row per source table: where the last successful copy stopped.
IF OBJECT_ID(N'etl.Watermark', N'U') IS NULL
BEGIN
    CREATE TABLE etl.Watermark (
        TableName      sysname      NOT NULL CONSTRAINT PK_Watermark PRIMARY KEY,
        WatermarkValue datetime2(0) NOT NULL
    );
    INSERT INTO etl.Watermark (TableName, WatermarkValue) VALUES (N'dbo.PurchaseRequests', '1900-01-01T00:00:00');
END
GO

CREATE OR ALTER PROCEDURE etl.usp_write_watermark @TableName sysname, @NewWatermark datetime2(0)
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE etl.Watermark SET WatermarkValue = @NewWatermark WHERE TableName = @TableName;
    IF @@ROWCOUNT = 0 THROW 50001, 'No watermark row for this table.', 1;
END
GO

-- The factory's system-assigned managed identity: read the source table, read and move the watermark, nothing else.
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'$(AdfName)')
    CREATE USER [$(AdfName)] FROM EXTERNAL PROVIDER;
GO
GRANT SELECT ON dbo.PurchaseRequests TO [$(AdfName)];
GRANT SELECT ON etl.Watermark TO [$(AdfName)];
GRANT EXECUTE ON etl.usp_write_watermark TO [$(AdfName)];
GO
