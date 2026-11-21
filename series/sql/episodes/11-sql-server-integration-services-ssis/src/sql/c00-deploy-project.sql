-- c00-deploy-project.sql
-- SQL Server only. Run on CON-SQL01 (SSMS connected to it) after the project was built in Visual Studio:
-- Build produces PartnerSalesProject.ispac; copy it to C:\MGLab\ssis\ on CON-SQL01 first.
-- Same thing as Visual Studio's Deploy / the Integration Services Deployment Wizard, but scripted
-- (catalog.deploy_project with the .ispac as varbinary(max), the pattern shown on Learn).
USE SSISDB;
GO
IF NOT EXISTS (SELECT 1 FROM catalog.folders WHERE name = N'MGLab')
    EXEC catalog.create_folder @folder_name = N'MGLab';
GO
DECLARE @ProjectBinary varbinary(max) =
    (SELECT BulkColumn FROM OPENROWSET(BULK 'C:\MGLab\ssis\PartnerSalesProject.ispac', SINGLE_BLOB) AS ispac);
DECLARE @operation_id bigint;
EXEC catalog.deploy_project @folder_name = N'MGLab', @project_name = N'PartnerSalesProject',
                            @project_stream = @ProjectBinary, @operation_id = @operation_id OUTPUT;
GO
-- c00 result: the package is in the catalog
SELECT f.name AS FolderName, p.name AS ProjectName, k.name AS PackageName
FROM catalog.folders AS f
JOIN catalog.projects AS p ON p.folder_id = f.folder_id
JOIN catalog.packages AS k ON k.project_id = p.project_id
WHERE f.name = N'MGLab';
GO
