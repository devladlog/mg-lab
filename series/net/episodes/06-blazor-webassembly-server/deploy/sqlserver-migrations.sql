IF OBJECT_ID(N'[__EFMigrationsHistory]') IS NULL
BEGIN
    CREATE TABLE [__EFMigrationsHistory] (
        [MigrationId] nvarchar(150) NOT NULL,
        [ProductVersion] nvarchar(32) NOT NULL,
        CONSTRAINT [PK___EFMigrationsHistory] PRIMARY KEY ([MigrationId])
    );
END;
GO

BEGIN TRANSACTION;
IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261121040104_InitialCreate'
)
BEGIN
    CREATE TABLE [Departments] (
        [Id] int NOT NULL IDENTITY,
        [Code] nvarchar(8) NOT NULL,
        [Name] nvarchar(100) NOT NULL,
        CONSTRAINT [PK_Departments] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261121040104_InitialCreate'
)
BEGIN
    CREATE TABLE [ProjectRequests] (
        [Id] int NOT NULL IDENTITY,
        [Title] nvarchar(100) NOT NULL,
        [Budget] decimal(18,2) NOT NULL,
        [RequestedBy] nvarchar(254) NOT NULL,
        [Justification] nvarchar(2000) NULL,
        [Priority] nvarchar(16) NOT NULL,
        [Status] nvarchar(16) NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [DecidedBy] nvarchar(254) NULL,
        [DecidedAtUtc] datetime2 NULL,
        [DepartmentId] int NOT NULL,
        [Version] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_ProjectRequests] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_ProjectRequests_Departments_DepartmentId] FOREIGN KEY ([DepartmentId]) REFERENCES [Departments] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261121040104_InitialCreate'
)
BEGIN
    IF EXISTS (SELECT * FROM [sys].[identity_columns] WHERE [name] IN (N'Id', N'Code', N'Name') AND [object_id] = OBJECT_ID(N'[Departments]'))
        SET IDENTITY_INSERT [Departments] ON;
    EXEC(N'INSERT INTO [Departments] ([Id], [Code], [Name])
    VALUES (1, N''FIN'', N''Finance''),
    (2, N''IT'', N''Information Technology''),
    (3, N''OPS'', N''Operations'')');
    IF EXISTS (SELECT * FROM [sys].[identity_columns] WHERE [name] IN (N'Id', N'Code', N'Name') AND [object_id] = OBJECT_ID(N'[Departments]'))
        SET IDENTITY_INSERT [Departments] OFF;
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261121040104_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_Departments_Code] ON [Departments] ([Code]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261121040104_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ProjectRequests_DepartmentId] ON [ProjectRequests] ([DepartmentId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261121040104_InitialCreate'
)
BEGIN
    INSERT INTO [__EFMigrationsHistory] ([MigrationId], [ProductVersion])
    VALUES (N'20261121040104_InitialCreate', N'10.0.15');
END;

COMMIT;
GO

BEGIN TRANSACTION;
IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261121040125_AddStatusPriorityIndex'
)
BEGIN
    CREATE INDEX [IX_ProjectRequests_Status_Priority] ON [ProjectRequests] ([Status], [Priority]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261121040125_AddStatusPriorityIndex'
)
BEGIN
    INSERT INTO [__EFMigrationsHistory] ([MigrationId], [ProductVersion])
    VALUES (N'20261121040125_AddStatusPriorityIndex', N'10.0.15');
END;

COMMIT;
GO

