-- c04-errors.sql
-- SQL Server only. When an execution fails: the error messages of the last execution, in order.
-- message_type 120 = Error (catalog.operation_messages / catalog.event_messages).
USE SSISDB;
GO
SELECT TOP (20) em.event_message_id, em.package_name, em.message_source_name, em.message
FROM catalog.event_messages AS em
WHERE em.operation_id = (SELECT MAX(execution_id) FROM catalog.executions WHERE package_name = N'PartnerSalesLoad.dtsx')
  AND em.event_name = N'OnError'
ORDER BY em.event_message_id;
GO
