-- s05-row-level-security.sql
-- After 15-row-level-security.sql: the same procedure returns different rows to different callers.
-- The signed search too: signing adds permissions, it doesn't change who the caller is.
SET NOCOUNT ON;
DECLARE @rows TABLE (CustomerId int, CustomerName nvarchar(100), Region nvarchar(20));
DECLARE @seen TABLE (Step int, Caller sysname, Via nvarchar(60), CustomerId int, Region nvarchar(20));
DECLARE @callers TABLE (Step int, Caller sysname, Via nvarchar(60));

EXECUTE AS USER = N'sales_north';
INSERT INTO @rows EXEC Sales.usp_ListCustomers;
REVERT;
INSERT INTO @callers VALUES (1, N'sales_north', N'usp_ListCustomers');
INSERT INTO @seen SELECT 1, N'sales_north', N'usp_ListCustomers', CustomerId, Region FROM @rows;
DELETE FROM @rows;

EXECUTE AS USER = N'sales_south';
INSERT INTO @rows EXEC Sales.usp_ListCustomers;
REVERT;
INSERT INTO @callers VALUES (2, N'sales_south', N'usp_ListCustomers');
INSERT INTO @seen SELECT 2, N'sales_south', N'usp_ListCustomers', CustomerId, Region FROM @rows;
DELETE FROM @rows;

INSERT INTO @rows EXEC Sales.usp_ListCustomers;              -- the runner's login: a db_owner member
INSERT INTO @callers VALUES (3, N'db_owner member', N'usp_ListCustomers');
INSERT INTO @seen SELECT 3, N'db_owner member', N'usp_ListCustomers', CustomerId, Region FROM @rows;
DELETE FROM @rows;

EXECUTE AS USER = N'sales_north';
INSERT INTO @rows EXEC Sales.usp_SearchCustomers @NamePrefix = N'Bruno';   -- Bruno Test is in Centre
REVERT;
INSERT INTO @callers VALUES (4, N'sales_north', N'usp_SearchCustomers ''Bruno''');
INSERT INTO @seen SELECT 4, N'sales_north', N'usp_SearchCustomers ''Bruno''', CustomerId, Region FROM @rows;

SELECT c.Caller,
       c.Via,
       (SELECT COUNT(*) FROM @seen AS s WHERE s.Step = c.Step) AS RowsSeen,
       (SELECT STRING_AGG(r.Region, N', ') WITHIN GROUP (ORDER BY r.Region)
          FROM (SELECT DISTINCT s.Region FROM @seen AS s WHERE s.Step = c.Step) AS r) AS Regions
FROM @callers AS c
ORDER BY c.Step;
