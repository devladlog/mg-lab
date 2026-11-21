-- c01-environment.sql
-- SQL Server only. A catalog environment with one variable, referenced by the project, so that the SQL Server name
-- is a setting of the server and not of the package. Re-runnable.
USE SSISDB;
GO
IF NOT EXISTS (SELECT 1 FROM catalog.environments AS e JOIN catalog.folders AS f ON f.folder_id = e.folder_id
               WHERE f.name = N'MGLab' AND e.name = N'Lab')
    EXEC catalog.create_environment @folder_name = N'MGLab', @environment_name = N'Lab';
GO
IF NOT EXISTS (SELECT 1 FROM catalog.environment_variables AS v JOIN catalog.environments AS e ON e.environment_id = v.environment_id
               WHERE e.name = N'Lab' AND v.name = N'ServerName')
    EXEC catalog.create_environment_variable @folder_name = N'MGLab', @environment_name = N'Lab',
         @variable_name = N'ServerName', @data_type = N'String', @sensitive = 0, @value = N'localhost',
         @description = N'SQL Server that holds ContosoBikesEtl, as seen from the SSIS server';
GO
IF NOT EXISTS (SELECT 1 FROM catalog.environment_references AS r JOIN catalog.projects AS p ON p.project_id = r.project_id
               WHERE p.name = N'PartnerSalesProject' AND r.environment_name = N'Lab')
    EXEC catalog.create_environment_reference @folder_name = N'MGLab', @project_name = N'PartnerSalesProject',
         @environment_name = N'Lab', @reference_type = 'R';
GO
-- the package parameter ServerName now takes its value from the environment variable of the same name
EXEC catalog.set_object_parameter_value @object_type = 30, @folder_name = N'MGLab', @project_name = N'PartnerSalesProject',
     @parameter_name = N'ServerName', @parameter_value = N'ServerName', @object_name = N'PartnerSalesLoad.dtsx', @value_type = 'R';
GO
-- c01 result
SELECT e.name AS EnvironmentName, v.name AS VariableName, CONVERT(nvarchar(100), v.value) AS VariableValue
FROM catalog.environments AS e
JOIN catalog.environment_variables AS v ON v.environment_id = e.environment_id
WHERE e.name = N'Lab';
GO
