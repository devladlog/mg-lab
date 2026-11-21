-- s06-rls-place-order.sql
-- Row-level security inside a procedure that writes: sales_north can place an order for a North customer;
-- a South customer is invisible to her, so the procedure's own check says "Unknown customer."
-- And the ownership chain covers the procedure, not the tables: a direct INSERT is denied.
SET NOCOUNT ON;
DECLARE @result TABLE (Step int, Caller sysname, Attempt nvarchar(80), Outcome nvarchar(20), Detail nvarchar(200));
DECLARE @lines Sales.OrderLineList;
INSERT INTO @lines (ProductId, Qty) VALUES (5, 1);
DECLARE @newOrderId int;

EXECUTE AS USER = N'sales_north';

BEGIN TRY
    EXEC Sales.usp_PlaceOrder @CustomerId = 1, @Lines = @lines, @OrderId = @newOrderId OUTPUT;   -- Alex Demo, North
    INSERT INTO @result VALUES (1, USER_NAME(), N'usp_PlaceOrder for customer 1 (North)', N'allowed',
                                CASE WHEN @newOrderId >= 2001 THEN N'new order placed' ELSE N'no order number' END);
END TRY
BEGIN CATCH
    INSERT INTO @result VALUES (1, USER_NAME(), N'usp_PlaceOrder for customer 1 (North)', N'error',
                                CONCAT(N'error ', ERROR_NUMBER(), N': ', ERROR_MESSAGE()));
END CATCH;

BEGIN TRY
    EXEC Sales.usp_PlaceOrder @CustomerId = 5, @Lines = @lines, @OrderId = @newOrderId OUTPUT;   -- Diego Placeholder, South
    INSERT INTO @result VALUES (2, USER_NAME(), N'usp_PlaceOrder for customer 5 (South)', N'allowed', N'new order placed');
END TRY
BEGIN CATCH
    INSERT INTO @result VALUES (2, USER_NAME(), N'usp_PlaceOrder for customer 5 (South)', N'error',
                                CONCAT(N'error ', ERROR_NUMBER(), N': ', ERROR_MESSAGE()));
END CATCH;

BEGIN TRY
    INSERT INTO Sales.Orders (OrderId, CustomerId, OrderDate, Status) VALUES (9999, 1, '2025-06-01', N'Placed');
    INSERT INTO @result VALUES (3, USER_NAME(), N'INSERT INTO Sales.Orders', N'allowed', N'');
END TRY
BEGIN CATCH
    INSERT INTO @result VALUES (3, USER_NAME(), N'INSERT INTO Sales.Orders', N'denied', CONCAT(N'error ', ERROR_NUMBER()));
END CATCH;

REVERT;

SELECT Caller, Attempt, Outcome, Detail FROM @result ORDER BY Step;
