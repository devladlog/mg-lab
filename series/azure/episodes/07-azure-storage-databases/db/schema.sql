CREATE TABLE [Orders] (
    [Id] bigint NOT NULL IDENTITY,
    [CustomerId] nvarchar(64) NOT NULL,
    [IdempotencyKey] nvarchar(64) NOT NULL,
    [RequestHash] char(64) NOT NULL,
    [CreatedUtc] datetime2 NOT NULL,
    [Status] varchar(16) NOT NULL,
    [Total] decimal(10,2) NOT NULL,
    [Version] uniqueidentifier NOT NULL,
    CONSTRAINT [PK_Orders] PRIMARY KEY ([Id])
);
GO


CREATE TABLE [OrderLines] (
    [Id] bigint NOT NULL IDENTITY,
    [OrderId] bigint NOT NULL,
    [Sku] varchar(7) NOT NULL,
    [Quantity] int NOT NULL,
    [UnitPrice] decimal(10,2) NOT NULL,
    CONSTRAINT [PK_OrderLines] PRIMARY KEY ([Id]),
    CONSTRAINT [FK_OrderLines_Orders_OrderId] FOREIGN KEY ([OrderId]) REFERENCES [Orders] ([Id]) ON DELETE CASCADE
);
GO


CREATE INDEX [IX_OrderLines_OrderId] ON [OrderLines] ([OrderId]);
GO


CREATE INDEX [IX_Orders_CustomerId_CreatedUtc_Id] ON [Orders] ([CustomerId], [CreatedUtc] DESC, [Id] DESC);
GO


CREATE UNIQUE INDEX [IX_Orders_IdempotencyKey] ON [Orders] ([IdempotencyKey]);
GO


