-- 03-procedures.sql
-- SQL Server only. The order-placing API: a table type for the lines, the safe procedure and the naive one.
-- Re-runnable: a table type can't be altered, so the procedures that use it are dropped first.

DROP PROCEDURE IF EXISTS Sales.usp_PlaceOrder;
DROP PROCEDURE IF EXISTS Sales.usp_PlaceOrder_Naive;
DROP TYPE IF EXISTS Sales.OrderLineList;
GO

-- One row per product: the client sends the whole order in one call (a table-valued parameter).
CREATE TYPE Sales.OrderLineList AS TABLE
(
    ProductId   int          NOT NULL PRIMARY KEY,
    Qty         int          NOT NULL CHECK (Qty > 0),
    DiscountPct decimal(5,2) NOT NULL DEFAULT (0)
);
GO

-- The safe version: all or nothing.
CREATE OR ALTER PROCEDURE Sales.usp_PlaceOrder
    @CustomerId int,
    @Lines      Sales.OrderLineList READONLY,
    @OrderId    int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;      -- any run-time error rolls back the whole transaction

    BEGIN TRY
        IF NOT EXISTS (SELECT 1 FROM Sales.Customers WHERE CustomerId = @CustomerId)
            THROW 50001, N'Unknown customer.', 1;
        IF NOT EXISTS (SELECT 1 FROM @Lines)
            THROW 50002, N'An order needs at least one line.', 1;
        IF EXISTS (SELECT 1 FROM @Lines AS l WHERE NOT EXISTS (SELECT 1 FROM Sales.Products AS p WHERE p.ProductId = l.ProductId))
            THROW 50003, N'Unknown product.', 1;

        BEGIN TRANSACTION;

        SET @OrderId = NEXT VALUE FOR Sales.OrderNumbers;

        INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status)
        VALUES (@OrderId, @CustomerId, CAST(SYSDATETIME() AS date), N'Placed');

        INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct)
        SELECT @OrderId, ROW_NUMBER() OVER (ORDER BY l.ProductId), l.ProductId, l.Qty, p.ListPrice, l.DiscountPct
        FROM @Lines AS l
        JOIN Sales.Products AS p ON p.ProductId = l.ProductId;

        -- No "check stock, then update": the CHECK constraint (StockQty >= 0) refuses to sell what we don't have.
        UPDATE p
        SET p.StockQty = p.StockQty - l.Qty
        FROM Sales.Products AS p
        JOIN @Lines AS l ON l.ProductId = p.ProductId;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        SET @OrderId = NULL;
        THROW;              -- re-raise the original error: number, message, line
    END CATCH;
END;
GO

-- The naive version: same statements, inside a transaction, but no XACT_ABORT and no TRY/CATCH.
-- When the UPDATE violates the CHECK constraint, only that statement is rolled back. The procedure
-- carries on to COMMIT, and the order and its lines are saved without the stock ever moving.
CREATE OR ALTER PROCEDURE Sales.usp_PlaceOrder_Naive
    @CustomerId int,
    @Lines      Sales.OrderLineList READONLY,
    @OrderId    int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRANSACTION;

    SET @OrderId = NEXT VALUE FOR Sales.OrderNumbers;

    INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status)
    VALUES (@OrderId, @CustomerId, CAST(SYSDATETIME() AS date), N'Placed');

    INSERT INTO Sales.OrderLines (OrderId, LineNumber, ProductId, Qty, UnitPrice, DiscountPct)
    SELECT @OrderId, ROW_NUMBER() OVER (ORDER BY l.ProductId), l.ProductId, l.Qty, p.ListPrice, l.DiscountPct
    FROM @Lines AS l
    JOIN Sales.Products AS p ON p.ProductId = l.ProductId;

    UPDATE p
    SET p.StockQty = p.StockQty - l.Qty
    FROM Sales.Products AS p
    JOIN @Lines AS l ON l.ProductId = p.ProductId;

    COMMIT TRANSACTION;
END;
GO
