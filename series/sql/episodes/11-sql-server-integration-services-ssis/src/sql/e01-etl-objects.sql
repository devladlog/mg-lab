-- e01-etl-objects.sql
-- Run in ContosoBikesEtl after 01-schema-and-data.sql. Re-runnable.
-- What the SSIS package PartnerSalesLoad.dtsx needs on the SQL Server side:
--   Stg.PartnerSales      landing table of the data flow (valid rows only)
--   Etl.RejectedRows      rows that failed a rule, with the reason (data flow + procedure)
--   Etl.RunLog            one row per package run: counts and times
--   Sales.PartnerSales    the real target: one row per dealer order line
-- The package only moves rows; the rules that decide inserted/updated/rejected live in the procedure, so they
-- can be tested without SSIS. The statements between "-- merge-begin" and "-- merge-end" are plain, portable
-- T-SQL: the local check runs them on DuckDB.
-- sqlserver only
IF SCHEMA_ID(N'Stg') IS NULL EXEC (N'CREATE SCHEMA Stg');
GO
-- sqlserver only
IF SCHEMA_ID(N'Etl') IS NULL EXEC (N'CREATE SCHEMA Etl');
GO

DROP PROCEDURE IF EXISTS Etl.usp_MergePartnerSales;
DROP PROCEDURE IF EXISTS Etl.usp_PrepareLoad;
DROP TABLE IF EXISTS Etl.RejectedRows;
DROP TABLE IF EXISTS Sales.PartnerSales;
DROP TABLE IF EXISTS Stg.PartnerSales;
DROP TABLE IF EXISTS Etl.RunLog;
GO

CREATE TABLE Etl.RunLog (
    RunLogId     int IDENTITY(1,1) NOT NULL CONSTRAINT PK_RunLog PRIMARY KEY,
    ExecutionId  bigint        NOT NULL,   -- catalog execution id (System::ServerExecutionID); 0 when run from Visual Studio
    SourceFile   nvarchar(260) NOT NULL,
    StartedAt    datetime2(0)  NOT NULL CONSTRAINT DF_RunLog_StartedAt DEFAULT SYSDATETIME(),
    FinishedAt   datetime2(0)  NULL,
    RowsStaged   int           NULL,
    RowsRejected int           NULL,
    LinesInserted int          NULL,
    LinesUpdated int           NULL
);
GO

CREATE TABLE Stg.PartnerSales (
    DealerCode      nvarchar(10)  NOT NULL,
    PartnerOrderRef nvarchar(20)  NOT NULL,
    LineNumber      int           NOT NULL,
    SaleDate        date          NOT NULL,
    ProductId       int           NOT NULL,
    Quantity        int           NOT NULL,
    UnitPrice       decimal(10,2) NOT NULL
);
GO

CREATE TABLE Etl.RejectedRows (
    RejectedId      int IDENTITY(1,1) NOT NULL CONSTRAINT PK_RejectedRows PRIMARY KEY,
    RunLogId        int           NULL CONSTRAINT FK_RejectedRows_RunLog REFERENCES Etl.RunLog (RunLogId),
    DealerCode      nvarchar(10)  NULL,
    PartnerOrderRef nvarchar(20)  NULL,
    LineNumber      int           NULL,
    SaleDate        date          NULL,
    ProductId       int           NULL,
    Quantity        int           NULL,
    UnitPrice       decimal(10,2) NULL,
    Reason          nvarchar(200) NULL     -- NULL right after the data flow; the procedure stamps run and reason
);
GO

CREATE TABLE Sales.PartnerSales (
    DealerCode      nvarchar(10)  NOT NULL,
    PartnerOrderRef nvarchar(20)  NOT NULL,
    LineNumber      int           NOT NULL,
    SaleDate        date          NOT NULL,
    ProductId       int           NOT NULL CONSTRAINT FK_PartnerSales_Products REFERENCES Sales.Products (ProductId),
    Qty             int           NOT NULL CONSTRAINT CK_PartnerSales_Qty CHECK (Qty > 0),
    UnitPrice       decimal(10,2) NOT NULL CONSTRAINT CK_PartnerSales_UnitPrice CHECK (UnitPrice >= 0),
    LoadedRunLogId  int           NOT NULL CONSTRAINT FK_PartnerSales_RunLog REFERENCES Etl.RunLog (RunLogId),
    CONSTRAINT PK_PartnerSales PRIMARY KEY (DealerCode, PartnerOrderRef, LineNumber)
);
GO

-- First task of the package: empty the landing table and open a run.
CREATE OR ALTER PROCEDURE Etl.usp_PrepareLoad
    @ExecutionId bigint,
    @SourceFile  nvarchar(260)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    TRUNCATE TABLE Stg.PartnerSales;
    INSERT INTO Etl.RunLog (ExecutionId, SourceFile) VALUES (@ExecutionId, @SourceFile);
END
GO

-- Last task of the package: decide what happens to every staged row. Safe to run twice on the same file:
-- the second run finds every line already present and unchanged, so it inserts and updates nothing.
CREATE OR ALTER PROCEDURE Etl.usp_MergePartnerSales
    @ExecutionId bigint
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    DECLARE @RunLogId int = (SELECT MAX(RunLogId) FROM Etl.RunLog WHERE ExecutionId = @ExecutionId);
    DECLARE @Staged int = (SELECT COUNT(*) FROM Stg.PartnerSales);
    DECLARE @Rejected int, @Inserted int, @Updated int;
    IF @RunLogId IS NULL
        THROW 50001, N'Etl.usp_PrepareLoad has not opened a run for this execution id.', 1;

    BEGIN TRANSACTION;
    -- merge-begin
    -- step: stamp-flow-rejects (rows the Conditional Split sent to Etl.RejectedRows have no run and no reason yet)
    UPDATE Etl.RejectedRows SET RunLogId = @RunLogId, Reason = N'Quantity must be positive and UnitPrice not negative' WHERE RunLogId IS NULL;
    SET @Rejected = @@ROWCOUNT;
    -- step: reject-unknown-products
    INSERT INTO Etl.RejectedRows (RunLogId, DealerCode, PartnerOrderRef, LineNumber, SaleDate, ProductId, Quantity, UnitPrice, Reason)
    SELECT @RunLogId, s.DealerCode, s.PartnerOrderRef, s.LineNumber, s.SaleDate, s.ProductId, s.Quantity, s.UnitPrice, N'Unknown ProductId'
    FROM Stg.PartnerSales AS s
    WHERE NOT EXISTS (SELECT 1 FROM Sales.Products AS p WHERE p.ProductId = s.ProductId);
    SET @Rejected += @@ROWCOUNT;
    -- step: update-changed-lines (a dealer corrected a line that was loaded before)
    UPDATE Sales.PartnerSales
    SET SaleDate = (SELECT s.SaleDate FROM Stg.PartnerSales AS s WHERE s.DealerCode = PartnerSales.DealerCode AND s.PartnerOrderRef = PartnerSales.PartnerOrderRef AND s.LineNumber = PartnerSales.LineNumber),
        ProductId = (SELECT s.ProductId FROM Stg.PartnerSales AS s WHERE s.DealerCode = PartnerSales.DealerCode AND s.PartnerOrderRef = PartnerSales.PartnerOrderRef AND s.LineNumber = PartnerSales.LineNumber),
        Qty = (SELECT s.Quantity FROM Stg.PartnerSales AS s WHERE s.DealerCode = PartnerSales.DealerCode AND s.PartnerOrderRef = PartnerSales.PartnerOrderRef AND s.LineNumber = PartnerSales.LineNumber),
        UnitPrice = (SELECT s.UnitPrice FROM Stg.PartnerSales AS s WHERE s.DealerCode = PartnerSales.DealerCode AND s.PartnerOrderRef = PartnerSales.PartnerOrderRef AND s.LineNumber = PartnerSales.LineNumber),
        LoadedRunLogId = @RunLogId
    WHERE EXISTS (SELECT 1 FROM Stg.PartnerSales AS s
                  WHERE s.DealerCode = PartnerSales.DealerCode AND s.PartnerOrderRef = PartnerSales.PartnerOrderRef AND s.LineNumber = PartnerSales.LineNumber
                    AND (s.SaleDate <> PartnerSales.SaleDate OR s.ProductId <> PartnerSales.ProductId OR s.Quantity <> PartnerSales.Qty OR s.UnitPrice <> PartnerSales.UnitPrice)
                    AND EXISTS (SELECT 1 FROM Sales.Products AS p WHERE p.ProductId = s.ProductId));
    SET @Updated = @@ROWCOUNT;
    -- step: insert-new-lines
    INSERT INTO Sales.PartnerSales (DealerCode, PartnerOrderRef, LineNumber, SaleDate, ProductId, Qty, UnitPrice, LoadedRunLogId)
    SELECT s.DealerCode, s.PartnerOrderRef, s.LineNumber, s.SaleDate, s.ProductId, s.Quantity, s.UnitPrice, @RunLogId
    FROM Stg.PartnerSales AS s
    WHERE EXISTS (SELECT 1 FROM Sales.Products AS p WHERE p.ProductId = s.ProductId)
      AND NOT EXISTS (SELECT 1 FROM Sales.PartnerSales AS t
                      WHERE t.DealerCode = s.DealerCode AND t.PartnerOrderRef = s.PartnerOrderRef AND t.LineNumber = s.LineNumber);
    SET @Inserted = @@ROWCOUNT;
    -- merge-end
    UPDATE Etl.RunLog
    SET FinishedAt = SYSDATETIME(), RowsStaged = @Staged, RowsRejected = @Rejected, LinesInserted = @Inserted, LinesUpdated = @Updated
    WHERE RunLogId = @RunLogId;
    COMMIT TRANSACTION;
END
GO
