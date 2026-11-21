CREATE TABLE [AuditEntries] (
    [Id] bigint NOT NULL IDENTITY,
    [RequestId] uniqueidentifier NOT NULL,
    [Action] varchar(32) NOT NULL,
    [ActorOid] varchar(36) NOT NULL,
    [Detail] nvarchar(400) NOT NULL,
    [AtUtc] datetime2 NOT NULL,
    [CorrelationId] varchar(64) NOT NULL,
    CONSTRAINT [PK_AuditEntries] PRIMARY KEY ([Id])
);
GO


CREATE TABLE [PurchaseRequests] (
    [Id] uniqueidentifier NOT NULL,
    [Title] nvarchar(120) NOT NULL,
    [Justification] nvarchar(2000) NOT NULL,
    [Amount] decimal(18,2) NOT NULL,
    [Currency] char(3) NOT NULL,
    [RequestedByOid] varchar(36) NOT NULL,
    [RequestedByName] nvarchar(200) NOT NULL,
    [CreatedAtUtc] datetime2 NOT NULL,
    [Status] varchar(16) NOT NULL,
    [DecidedByOid] varchar(36) NULL,
    [DecidedByName] nvarchar(200) NULL,
    [DecidedAtUtc] datetime2 NULL,
    [DecisionComment] nvarchar(500) NULL,
    [Version] int NOT NULL,
    CONSTRAINT [PK_PurchaseRequests] PRIMARY KEY ([Id])
);
GO


CREATE INDEX [IX_AuditEntries_RequestId] ON [AuditEntries] ([RequestId]);
GO


CREATE INDEX [IX_PurchaseRequests_RequestedByOid] ON [PurchaseRequests] ([RequestedByOid]);
GO


CREATE INDEX [IX_PurchaseRequests_Status] ON [PurchaseRequests] ([Status]);
GO
