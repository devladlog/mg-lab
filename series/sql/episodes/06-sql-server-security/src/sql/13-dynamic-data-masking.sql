-- 13-dynamic-data-masking.sql
-- SQL Server only, part of the setup (it runs before row-level security exists). Masks the email address for
-- everyone without UNMASK; db_owner members keep seeing it.
-- Learn: adding a mask is a schema change and fails on a column other objects depend on, such as an index.
-- Email has a UNIQUE constraint (an index), so the constraint is dropped, the mask added, the constraint re-created.

ALTER TABLE Sales.Customers DROP CONSTRAINT UQ_Customers_Email;
ALTER TABLE Sales.Customers ALTER COLUMN Email ADD MASKED WITH (FUNCTION = 'email()');
ALTER TABLE Sales.Customers ADD CONSTRAINT UQ_Customers_Email UNIQUE (Email);
GO
