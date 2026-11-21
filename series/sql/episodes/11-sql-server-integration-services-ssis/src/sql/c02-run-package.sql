-- c02-run-package.sql
-- SQL Server only. Runs PartnerSalesLoad.dtsx from the catalog and waits for it (SYNCHRONIZED).
-- Change the two DECLARE lines to run it again: the logging level (1 = Basic, the default; 3 = Verbose) and the file.
USE SSISDB;
GO
DECLARE @LoggingLevel smallint = 1;
DECLARE @InputFile nvarchar(260) = N'C:\MGLab\ssis\in\partner-sales-2025-05-21.csv';
DECLARE @reference_id bigint =
    (SELECT r.reference_id FROM catalog.environment_references AS r JOIN catalog.projects AS p ON p.project_id = r.project_id
     WHERE p.name = N'PartnerSalesProject' AND r.environment_name = N'Lab');
DECLARE @execution_id bigint;
EXEC catalog.create_execution @folder_name = N'MGLab', @project_name = N'PartnerSalesProject', @package_name = N'PartnerSalesLoad.dtsx',
     @reference_id = @reference_id, @use32bitruntime = 0, @execution_id = @execution_id OUTPUT;
EXEC catalog.set_execution_parameter_value @execution_id, @object_type = 50, @parameter_name = N'LOGGING_LEVEL', @parameter_value = @LoggingLevel;
EXEC catalog.set_execution_parameter_value @execution_id, @object_type = 50, @parameter_name = N'SYNCHRONIZED', @parameter_value = 1;
EXEC catalog.set_execution_parameter_value @execution_id, @object_type = 30, @parameter_name = N'InputFile', @parameter_value = @InputFile;
EXEC catalog.start_execution @execution_id;
GO
