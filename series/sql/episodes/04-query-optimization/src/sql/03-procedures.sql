-- 03-procedures.sql
-- The customer order list, as the app calls it: a stored procedure with one parameter.
-- Customer 1 (Contoso Megastore) has 60,000 orders; a typical customer has about 7.
-- SQL Server compiles the procedure for the value of @CustomerId it sees on the first call
-- (parameter sniffing) and reuses that plan for every value until it is recompiled.
CREATE OR ALTER PROCEDURE Sales.GetCustomerOrders
    @CustomerId int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT OrderId, OrderDate, Status, TotalAmount, ShipCountry
    FROM Sales.Orders
    WHERE CustomerId = @CustomerId
    ORDER BY OrderDate DESC, OrderId DESC;
END;
GO
-- Same query, compiled on every call for the actual value: the best plan each time, at the cost of a
-- compilation per execution (Learn: assess the impact on the whole workload before using RECOMPILE).
CREATE OR ALTER PROCEDURE Sales.GetCustomerOrders_Recompile
    @CustomerId int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT OrderId, OrderDate, Status, TotalAmount, ShipCountry
    FROM Sales.Orders
    WHERE CustomerId = @CustomerId
    ORDER BY OrderDate DESC, OrderId DESC
    OPTION (RECOMPILE);
END;
GO
