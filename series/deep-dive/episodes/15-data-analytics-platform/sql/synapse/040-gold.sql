-- Gold: a star schema for Power BI. Serverless SQL has no tables, so every object is a view over the lake.
-- (There is no date dimension here on purpose: Power BI builds a contiguous calendar in the model, episode 16.)
CREATE OR ALTER VIEW gold.DimDepartment AS
SELECT d.DepartmentCode AS DepartmentKey, d.DepartmentName
FROM ref.Department AS d;
GO

CREATE OR ALTER VIEW gold.FactPurchaseRequest AS
SELECT
    s.RequestId,
    s.DepartmentCode AS DepartmentKey,
    s.Category,
    s.VendorName,
    s.Amount,
    s.Currency,
    s.Status,
    CAST(s.SubmittedOn AS date) AS SubmittedDate,
    CAST(s.ApprovedOn  AS date) AS ApprovedDate,
    DATEDIFF(day, CAST(s.SubmittedOn AS date), CAST(s.ApprovedOn AS date)) AS CycleDays,
    CASE WHEN s.Status <> 'Approved' THEN NULL
         WHEN DATEDIFF(day, CAST(s.SubmittedOn AS date), CAST(s.ApprovedOn AS date)) > 5 THEN 1
         ELSE 0 END AS SlaBreached,
    DATEDIFF(day, CAST('1900-01-01' AS date), CAST(s.SubmittedOn AS date)) % 7 AS SubmittedWeekday   -- 0 = Monday (1 Jan 1900 was a Monday), independent of DATEFIRST
FROM silver.PurchaseRequest AS s
WHERE s.IsValid = 1;
GO

CREATE OR ALTER VIEW gold.DepartmentMonthly AS
SELECT
    f.DepartmentKey,
    DATEFROMPARTS(YEAR(f.SubmittedDate), MONTH(f.SubmittedDate), 1) AS MonthStart,
    COUNT(*)                                             AS Requests,
    SUM(f.Amount)                                        AS Spend,
    SUM(CASE WHEN f.Status = 'Approved' THEN 1 ELSE 0 END) AS ApprovedRequests,
    AVG(CAST(f.CycleDays AS float))                      AS AvgCycleDays,
    SUM(CASE WHEN f.SlaBreached = 1 THEN 1 ELSE 0 END)   AS SlaBreaches
FROM gold.FactPurchaseRequest AS f
GROUP BY f.DepartmentKey, DATEFROMPARTS(YEAR(f.SubmittedDate), MONTH(f.SubmittedDate), 1);
GO
