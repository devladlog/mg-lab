-- q01: the order history page for one customer (customer 4242 has 7 orders).
-- The most common query in the app, and the table has no index on CustomerId:
-- the foreign key on CustomerId doesn't create one.
SELECT OrderId, OrderDate, TotalAmount
FROM Sales.Orders
WHERE CustomerId = 4242
ORDER BY OrderDate DESC;
