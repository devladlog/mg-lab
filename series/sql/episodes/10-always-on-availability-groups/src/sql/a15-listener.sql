-- a15-listener.sql
-- SQL Server only, OPTIONAL (needs a free static IP, 10.50.0.43 here, and the cluster name object's right to create
-- computer objects in AD: by default it can create only 10 virtual computer objects). Run on the primary. Clients
-- connect to agl-contoso instead of a server name, and the listener follows the primary through a failover.
USE master;
GO
ALTER AVAILABILITY GROUP ag_contoso ADD LISTENER 'agl-contoso' (WITH IP ((N'10.50.0.43', N'255.255.255.0')), PORT = 1433);
GO
SELECT l.dns_name AS Listener, l.port AS Port, i.ip_address AS IpAddress
FROM sys.availability_group_listeners AS l
JOIN sys.availability_group_listener_ip_addresses AS i ON i.listener_id = l.listener_id;
GO
