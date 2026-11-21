-- Simulates what incremental refresh has to cope with. Run it AFTER the first refresh, then refresh again.
SET NOCOUNT ON;
GO
-- 1. Corrections to the last three completed days: inside the refresh period, so the next refresh picks them up.
--    ModifiedDate moves, which is what the "detect data changes" polling expression looks at.
DECLARE @Today datetime2(0) = CAST(CAST(SYSUTCDATETIME() AS date) AS datetime2(0));
UPDATE dbo.Sales
SET UnitPrice = UnitPrice + 1.00, ModifiedDate = SYSUTCDATETIME()
WHERE OrderTimestamp >= DATEADD(day, -3, @Today) AND OrderTimestamp < @Today AND SalesId % 50 = 0;
SELECT @@ROWCOUNT AS corrected_recent_rows;
GO
-- 2. A correction to old data (a historical partition). The normal refresh does not look there, so the report keeps the old
--    value until you refresh that one partition (SSMS or the enhanced refresh API with an "objects" list).
UPDATE dbo.Sales
SET UnitPrice = UnitPrice + 1.00, ModifiedDate = SYSUTCDATETIME()
WHERE OrderTimestamp >= '2023-03-01' AND OrderTimestamp < '2023-04-01' AND SalesId % 100 = 0;
SELECT @@ROWCOUNT AS corrected_old_rows;
GO
