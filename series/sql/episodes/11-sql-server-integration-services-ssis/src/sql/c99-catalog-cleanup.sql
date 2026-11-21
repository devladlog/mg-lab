-- c99-catalog-cleanup.sql
-- SQL Server only. Tear-down of the catalog side: project, environment and folder of this episode.
-- (e00-reset.sql drops the ContosoBikesEtl database. SSISDB itself stays: other demos may use it.)
USE SSISDB;
GO
IF EXISTS (SELECT 1 FROM catalog.projects AS p JOIN catalog.folders AS f ON f.folder_id = p.folder_id WHERE f.name = N'MGLab' AND p.name = N'PartnerSalesProject')
    EXEC catalog.delete_project @folder_name = N'MGLab', @project_name = N'PartnerSalesProject';
GO
IF EXISTS (SELECT 1 FROM catalog.environments AS e JOIN catalog.folders AS f ON f.folder_id = e.folder_id WHERE f.name = N'MGLab' AND e.name = N'Lab')
    EXEC catalog.delete_environment @folder_name = N'MGLab', @environment_name = N'Lab';
GO
IF EXISTS (SELECT 1 FROM catalog.folders WHERE name = N'MGLab')
    EXEC catalog.delete_folder @folder_name = N'MGLab';
GO
