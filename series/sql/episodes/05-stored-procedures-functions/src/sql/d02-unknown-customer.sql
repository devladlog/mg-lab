-- d02-unknown-customer.sql
-- A business rule broken before anything is written: THROW 50001, caught here and shown as a row.
SET NOCOUNT ON;
DECLARE @lines Sales.OrderLineList;
INSERT INTO @lines (ProductId, Qty) VALUES (5, 1);

DECLARE @newOrderId int;
BEGIN TRY
    EXEC Sales.usp_PlaceOrder @CustomerId = 99, @Lines = @lines, @OrderId = @newOrderId OUTPUT;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS ErrorNumber,
           ERROR_MESSAGE() AS ErrorMessage,
           @@TRANCOUNT AS OpenTransactions;
END CATCH;
