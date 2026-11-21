-- c03-results.sql
-- SQL Server only. What the last execution of PartnerSalesLoad.dtsx did: the catalog's view of it (status, data
-- flow row counts) next to what the package wrote in ContosoBikesEtl (Etl.RunLog, Sales.PartnerSales).
USE ContosoBikesEtl;
GO
DECLARE @exec bigint = (SELECT MAX(execution_id) FROM SSISDB.catalog.executions WHERE package_name = N'PartnerSalesLoad.dtsx');
DECLARE @run TABLE (RowsStaged int, RowsRejected int, LinesInserted int, LinesUpdated int);
INSERT INTO @run SELECT TOP (1) RowsStaged, RowsRejected, LinesInserted, LinesUpdated FROM Etl.RunLog WHERE ExecutionId = @exec ORDER BY RunLogId DESC;
SELECT Item, Value FROM (
    SELECT 1 AS Ord, N'Execution status' AS Item,
           CASE e.status WHEN 7 THEN N'Succeeded' WHEN 4 THEN N'Failed' WHEN 2 THEN N'Running' ELSE CONVERT(nvarchar(20), e.status) END AS Value
    FROM SSISDB.catalog.executions AS e WHERE e.execution_id = @exec
    UNION ALL SELECT 2, N'Rows staged',   CONVERT(nvarchar(20), RowsStaged)    FROM @run
    UNION ALL SELECT 3, N'Rows rejected', CONVERT(nvarchar(20), RowsRejected)  FROM @run
    UNION ALL SELECT 4, N'Lines inserted', CONVERT(nvarchar(20), LinesInserted) FROM @run
    UNION ALL SELECT 5, N'Lines updated', CONVERT(nvarchar(20), LinesUpdated)  FROM @run
    UNION ALL SELECT 6, N'Lines in Sales.PartnerSales', CONVERT(nvarchar(20), COUNT(*)) FROM Sales.PartnerSales
    UNION ALL SELECT 7, N'Rows sent by Flat File Source (data statistics)', CONVERT(nvarchar(20), COALESCE(SUM(rows_sent), 0))
              FROM SSISDB.catalog.execution_data_statistics WHERE execution_id = @exec AND source_component_name = N'Flat File Source'
) AS r ORDER BY Ord;
GO
