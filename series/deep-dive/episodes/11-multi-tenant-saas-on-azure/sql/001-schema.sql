-- Contoso purchase requests as a service: one shared database, one schema, tenant ID on every tenant-owned row.
-- Run as the SQL Entra admin. Idempotent: safe to run twice.

IF OBJECT_ID(N'dbo.Tenants', N'U') IS NULL
CREATE TABLE dbo.Tenants (
    TenantId   uniqueidentifier NOT NULL CONSTRAINT PK_Tenants PRIMARY KEY,   -- the customer's Entra tenant ID (token claim tid)
    Name       nvarchar(200)    NOT NULL,
    [Plan]     nvarchar(20)     NOT NULL CONSTRAINT DF_Tenants_Plan DEFAULT N'starter',
    Status     nvarchar(20)     NOT NULL CONSTRAINT DF_Tenants_Status DEFAULT N'active',
    CreatedUtc datetime2        NOT NULL
);
GO

IF OBJECT_ID(N'dbo.PurchaseRequests', N'U') IS NULL
CREATE TABLE dbo.PurchaseRequests (
    TenantId   uniqueidentifier NOT NULL CONSTRAINT FK_PurchaseRequests_Tenants REFERENCES dbo.Tenants (TenantId),
    Id         uniqueidentifier NOT NULL,
    Title      nvarchar(200)    NOT NULL,
    Amount     decimal(18, 2)   NOT NULL,
    Status     nvarchar(20)     NOT NULL,
    CreatedBy  nvarchar(64)     NOT NULL,   -- the caller's oid
    CreatedUtc datetime2        NOT NULL,
    CONSTRAINT PK_PurchaseRequests PRIMARY KEY (TenantId, Id)   -- tenant first: every lookup starts inside one tenant
);
GO
