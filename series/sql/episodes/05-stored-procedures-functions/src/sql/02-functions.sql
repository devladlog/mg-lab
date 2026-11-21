-- 02-functions.sql
-- SQL Server only (the local check inlines these functions itself, see proc_lab.py).
-- Three functions: an inlineable scalar UDF, a scalar UDF that can't be inlined, and an inline table-valued function.

-- Scalar UDF: one RETURN with a plain expression. At compatibility level 150+ SQL Server can inline it
-- into the calling query (sys.sql_modules.is_inlineable = 1; no UserDefinedFunction node in the actual plan).
CREATE OR ALTER FUNCTION Sales.ufn_LineTotal
(
    @Qty         int,
    @UnitPrice   decimal(10,2),
    @DiscountPct decimal(5,2)
)
RETURNS decimal(12,2)
AS
BEGIN
    RETURN CAST(@Qty * @UnitPrice * (100 - @DiscountPct) / 100 AS decimal(12,2));
END;
GO

-- The gotcha: GETDATE() is time-dependent, and a UDF that calls a time-dependent built-in is never
-- inlineable (is_inlineable = 0). It still works; it just runs once per row, the old way.
CREATE OR ALTER FUNCTION Sales.ufn_DaysSinceOrder
(
    @OrderDate date
)
RETURNS int
AS
BEGIN
    RETURN DATEDIFF(day, @OrderDate, CAST(GETDATE() AS date));
END;
GO

-- Inline table-valued function: a parameterized view. The optimizer expands its SELECT into the caller.
CREATE OR ALTER FUNCTION Sales.ufn_CustomerOrderSummary
(
    @CustomerId int
)
RETURNS TABLE
AS
RETURN
    SELECT o.OrderId,
           o.OrderDate,
           COUNT(*) AS Lines,
           SUM(Sales.ufn_LineTotal(l.Qty, l.UnitPrice, l.DiscountPct)) AS OrderTotal
    FROM Sales.Orders AS o
    JOIN Sales.OrderLines AS l ON l.OrderId = o.OrderId
    WHERE o.CustomerId = @CustomerId
    GROUP BY o.OrderId, o.OrderDate;
GO
