-- t01-config-review.sql
-- SQL Server only. Step 1 of any tuning session: what is this instance configured to do? Read-only.
-- sys.configurations lists every option (value_in_use is what is running now).
-- The defaults below are the ones on Learn's pages for each option: max server memory 2147483647 MB,
-- max degree of parallelism 0, cost threshold for parallelism 5. A default is where you start looking, not a diagnosis.
SELECT Item, Value, LearnDefault, Note
FROM (
    SELECT 1 AS Ord,
           c.name AS Item,
           CONVERT(nvarchar(20), c.value_in_use) AS Value,
           CONVERT(nvarchar(20), CASE c.name WHEN N'max server memory (MB)' THEN 2147483647
                                             WHEN N'max degree of parallelism' THEN 0
                                             WHEN N'cost threshold for parallelism' THEN 5 END) AS LearnDefault,
           CASE c.name
                WHEN N'max server memory (MB)' THEN
                     CASE WHEN c.value_in_use = 2147483647 THEN N'default: SQL Server may use all memory; set an upper limit'
                          ELSE N'limited' END
                WHEN N'max degree of parallelism' THEN
                     CASE WHEN c.value_in_use = 0 THEN N'default 0: all processors (up to 64); rarely the best value'
                          ELSE N'limited' END
                ELSE
                     CASE WHEN c.value_in_use = 5 THEN N'default 5: a starting point, not a recommendation'
                          ELSE N'changed' END
           END AS Note
    FROM sys.configurations AS c
    WHERE c.name IN (N'max server memory (MB)', N'max degree of parallelism', N'cost threshold for parallelism')
    UNION ALL
    SELECT 2, N'logical CPUs', CONVERT(nvarchar(20), i.cpu_count), NULL, NULL FROM sys.dm_os_sys_info AS i
    UNION ALL
    SELECT 3, N'physical memory (MB)', CONVERT(nvarchar(20), i.physical_memory_kb / 1024), NULL, NULL FROM sys.dm_os_sys_info AS i
) AS x
ORDER BY Ord, CASE Item WHEN N'max server memory (MB)' THEN 1 WHEN N'max degree of parallelism' THEN 2 ELSE 3 END;
