-- dmv-index-sizes: what each index on Sales.Orders costs in storage.
-- used_page_count includes in-row, LOB (columnstore segments) and row-overflow pages; one page = 8 KB.
SELECT i.name                                         AS IndexName,
       i.type_desc                                    AS IndexType,
       i.has_filter                                   AS Filtered,
       SUM(ps.row_count)                              AS IndexRows,
       SUM(ps.used_page_count)                        AS UsedPages,
       CAST(SUM(ps.used_page_count) / 128.0 AS decimal(10, 2)) AS UsedMB
FROM sys.dm_db_partition_stats AS ps
JOIN sys.indexes AS i
  ON i.object_id = ps.object_id AND i.index_id = ps.index_id
WHERE ps.object_id = OBJECT_ID(N'Sales.Orders')
GROUP BY i.index_id, i.name, i.type_desc, i.has_filter
ORDER BY i.index_id;
