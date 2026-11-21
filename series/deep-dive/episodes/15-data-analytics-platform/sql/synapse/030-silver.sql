-- Reference data kept in code: five departments.
CREATE OR ALTER VIEW ref.Department AS
SELECT d.DepartmentCode, d.DepartmentName
FROM (VALUES ('FIN', 'Finance'), ('HR', 'Human Resources'), ('IT', 'Information Technology'),
             ('MKT', 'Marketing'), ('OPS', 'Operations')) AS d (DepartmentCode, DepartmentName);
GO

-- Silver: the latest version of each request, with a reason when the row breaks a rule. Nothing is deleted here:
-- bad rows stay visible (quality.CheckResult) and simply do not reach gold.
CREATE OR ALTER VIEW silver.PurchaseRequest AS
WITH ranked AS (
    SELECT b.*, ROW_NUMBER() OVER (PARTITION BY b.RequestId ORDER BY b.ModifiedOn DESC) AS VersionRank
    FROM bronze.PurchaseRequest AS b
),
latest AS (
    SELECT RequestId, DepartmentCode, Category, VendorName, Amount, Currency, Status, SubmittedOn, ApprovedOn, ModifiedOn
    FROM ranked
    WHERE VersionRank = 1
),
checked AS (
    SELECT l.*,
        CASE WHEN l.Amount IS NULL OR l.Amount <= 0 THEN 'NonPositiveAmount'
             WHEN l.DepartmentCode NOT IN (SELECT DepartmentCode FROM ref.Department) THEN 'UnknownDepartment'
             WHEN l.Status NOT IN ('Submitted', 'Approved', 'Rejected') THEN 'UnknownStatus'
             WHEN l.Status = 'Approved' AND l.ApprovedOn IS NULL THEN 'ApprovedWithoutDate'
             WHEN l.ApprovedOn IS NOT NULL AND l.ApprovedOn < l.SubmittedOn THEN 'ApprovedBeforeSubmitted'
             ELSE NULL END AS RejectReason
    FROM latest AS l
)
SELECT c.RequestId, c.DepartmentCode, c.Category, c.VendorName, c.Amount, c.Currency, c.Status,
       c.SubmittedOn, c.ApprovedOn, c.ModifiedOn, c.RejectReason,
       CASE WHEN c.RejectReason IS NULL THEN 1 ELSE 0 END AS IsValid
FROM checked AS c;
GO
