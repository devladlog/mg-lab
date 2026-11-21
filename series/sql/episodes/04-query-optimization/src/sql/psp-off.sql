-- psp-off: turn off Parameter Sensitive Plan optimization for this database (SQL Server 2022, compat 160),
-- so the classic parameter sniffing problem reproduces. psp-on.sql puts the default back.
ALTER DATABASE SCOPED CONFIGURATION SET PARAMETER_SENSITIVE_PLAN_OPTIMIZATION = OFF;
