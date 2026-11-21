-- qs-forced-plans: forced plans and whether forcing is still working (from Learn's Query Store best
-- practices). If an index the plan needs is dropped, forcing fails and SQL Server compiles normally.
SELECT p.plan_id                       AS PlanId,
       p.query_id                      AS QueryId,
       OBJECT_NAME(q.object_id)        AS ContainingObject,
       p.force_failure_count           AS ForceFailureCount,
       p.last_force_failure_reason_desc AS LastForceFailureReason
FROM sys.query_store_plan AS p
JOIN sys.query_store_query AS q ON q.query_id = p.query_id
WHERE p.is_forced_plan = 1;
