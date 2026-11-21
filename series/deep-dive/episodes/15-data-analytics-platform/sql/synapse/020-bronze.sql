-- Bronze: the files exactly as Data Factory landed them, every version of every row, with the column types pinned.
-- This is the only place that knows where the files are.
CREATE OR ALTER VIEW bronze.PurchaseRequest AS
SELECT
    CAST(r.RequestId      AS int)            AS RequestId,
    CAST(r.DepartmentCode AS varchar(10))    AS DepartmentCode,
    CAST(r.Category       AS nvarchar(40))   AS Category,
    CAST(r.VendorName     AS nvarchar(100))  AS VendorName,
    CAST(r.Amount         AS decimal(18, 2)) AS Amount,
    CAST(r.Currency       AS char(3))        AS Currency,
    CAST(r.Status         AS varchar(20))    AS Status,
    CAST(r.SubmittedOn    AS datetime2(0))   AS SubmittedOn,
    CAST(r.ApprovedOn     AS datetime2(0))   AS ApprovedOn,
    CAST(r.ModifiedOn     AS datetime2(0))   AS ModifiedOn
FROM OPENROWSET(
        BULK 'bronze/purchase_requests/*/*.parquet',
        DATA_SOURCE = 'lake',
        FORMAT = 'PARQUET') AS r;
GO
