-- Quality report: one row per check. Any row with Severity = 'error' and RowTotal > 0 should stop a release.
CREATE OR ALTER VIEW quality.CheckResult AS
SELECT 'bronze row versions' AS CheckName, 'info' AS Severity, COUNT_BIG(*) AS RowTotal
FROM bronze.PurchaseRequest
UNION ALL
SELECT 'distinct requests', 'info', COUNT_BIG(*)
FROM silver.PurchaseRequest
UNION ALL
SELECT CONCAT('rejected: ', s.RejectReason), 'error', COUNT_BIG(*)
FROM silver.PurchaseRequest AS s
WHERE s.IsValid = 0
GROUP BY s.RejectReason;
GO
