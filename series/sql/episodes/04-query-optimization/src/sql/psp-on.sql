-- psp-on: the default at compatibility level 160 - PSP optimization may cache more than one plan for a
-- parameterized query (look for QueryVariantID in the plan).
ALTER DATABASE SCOPED CONFIGURATION SET PARAMETER_SENSITIVE_PLAN_OPTIMIZATION = ON;
