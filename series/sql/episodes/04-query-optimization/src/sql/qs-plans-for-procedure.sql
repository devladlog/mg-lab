-- qs-plans-for-procedure: every plan Query Store has recorded for the query inside
-- Sales.GetCustomerOrders, with its shape, executions and average logical reads.
-- Query Store keeps this across restarts; in-memory and on-disk data are combined when you read it.
WITH plans AS (
    SELECT p.query_id,
           p.plan_id,
           p.is_forced_plan,
           CASE WHEN p.query_plan LIKE N'%PhysicalOp="Key Lookup"%'           THEN N'seek + key lookup'
                WHEN p.query_plan LIKE N'%PhysicalOp="Clustered Index Scan"%' THEN N'clustered index scan'
                ELSE N'other' END AS PlanShape
    FROM sys.query_store_plan AS p
    JOIN sys.query_store_query AS q ON q.query_id = p.query_id
    WHERE q.object_id = OBJECT_ID(N'Sales.GetCustomerOrders')
)
SELECT pl.query_id                AS QueryId,
       pl.plan_id                 AS PlanId,
       pl.PlanShape,
       pl.is_forced_plan          AS IsForced,
       SUM(rs.count_executions)   AS Executions,
       CAST(SUM(rs.avg_logical_io_reads * rs.count_executions)
            / NULLIF(SUM(rs.count_executions), 0) AS decimal(12, 1)) AS AvgLogicalReads
FROM plans AS pl
LEFT JOIN sys.query_store_runtime_stats AS rs ON rs.plan_id = pl.plan_id
GROUP BY pl.query_id, pl.plan_id, pl.PlanShape, pl.is_forced_plan
ORDER BY pl.plan_id;
-- tune_lab.py then forces the clustered index scan plan from this list:
-- EXEC sp_query_store_force_plan @query_id = <QueryId>, @plan_id = <PlanId>;
