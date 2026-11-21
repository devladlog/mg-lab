-- q05: the whole org chart from one table, with a recursive CTE.
-- The anchor and recursive members must return the same data types, hence the CASTs on Path.
WITH org AS (
    SELECT EmployeeId, FullName, JobTitle, ManagerId,
           0 AS Lvl,
           CAST(FullName AS nvarchar(400)) AS Path
    FROM HR.Employees
    WHERE ManagerId IS NULL
    UNION ALL
    SELECT e.EmployeeId, e.FullName, e.JobTitle, e.ManagerId,
           o.Lvl + 1,
           CAST(CONCAT(o.Path, N' > ', e.FullName) AS nvarchar(400))
    FROM HR.Employees AS e
    JOIN org AS o ON e.ManagerId = o.EmployeeId
)
SELECT EmployeeId, FullName, JobTitle, Lvl, Path
FROM org
ORDER BY Path
OPTION (MAXRECURSION 10);   -- default is 100; a cycle in ManagerId fails fast instead of looping
