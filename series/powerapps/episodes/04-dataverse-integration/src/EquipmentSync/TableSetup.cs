using Microsoft.Crm.Sdk.Messages;
using Microsoft.PowerPlatform.Dataverse.Client;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Messages;
using Microsoft.Xrm.Sdk.Metadata;

namespace EquipmentSync;

/// <summary>
/// One-off setup on the Equipment table: an alternate key on the asset tag (so the register can upsert by tag) and
/// change tracking (so changes can flow back). Re-runnable: it checks first and only creates what's missing.
/// </summary>
public sealed class TableSetup(IOrganizationServiceAsync2 service, TextWriter log, Func<TimeSpan, CancellationToken, Task>? delay = null)
{
    private readonly Func<TimeSpan, CancellationToken, Task> delay = delay ?? Task.Delay;
    public TimeSpan PollInterval { get; init; } = TimeSpan.FromSeconds(5);
    public int MaxPolls { get; init; } = 60;

    public async Task EnsureAlternateKeyAsync(CancellationToken ct = default)
    {
        var table = await RetrieveTableAsync(ct);
        var existing = table.Keys?.FirstOrDefault(k => k.KeyAttributes.SequenceEqual([Equipment.AssetTag]));
        string keyName;
        if (existing != null)
        {
            keyName = existing.LogicalName;
            log.WriteLine($"Alternate key {keyName} exists ({existing.EntityKeyIndexStatus}).");
            if (existing.EntityKeyIndexStatus == EntityKeyIndexStatus.Active) return;
        }
        else
        {
            await service.ExecuteAsync(new CreateEntityKeyRequest
            {
                EntityName = Equipment.Table,
                EntityKey = new EntityKeyMetadata
                {
                    SchemaName = Equipment.KeySchemaName,
                    DisplayName = new Label("Asset tag key", 1033),
                    KeyAttributes = [Equipment.AssetTag],
                },
            }, ct);
            keyName = Equipment.KeyName;
            log.WriteLine($"Alternate key {keyName} created; the index is built in the background.");
        }

        // Learn: the index is created by a background job; EntityKeyIndexStatus goes Pending -> In Progress -> Active (or Failed).
        for (var poll = 0; poll < MaxPolls; poll++)
        {
            var key = ((RetrieveEntityKeyResponse)await service.ExecuteAsync(new RetrieveEntityKeyRequest
            {
                EntityLogicalName = Equipment.Table,
                LogicalName = keyName,
            }, ct)).EntityKeyMetadata;

            switch (key.EntityKeyIndexStatus)
            {
                case EntityKeyIndexStatus.Active:
                    log.WriteLine("Alternate key index is Active.");
                    return;
                case EntityKeyIndexStatus.Failed:
                    // Usually duplicate asset tags already in the table. Fix the data, then ReactivateEntityKey.
                    throw new InvalidOperationException(
                        $"Index creation for {keyName} failed (duplicate asset tags?). Fix the data, then reactivate the key (ReactivateEntityKeyRequest).");
                default:
                    log.WriteLine($"Index status: {key.EntityKeyIndexStatus}...");
                    await delay(PollInterval, ct);
                    break;
            }
        }
        throw new TimeoutException($"The index for {keyName} wasn't Active after {MaxPolls} checks.");
    }

    /// <summary>Learn: "After you enable change tracking for a table, you can't disable it." So it needs an explicit opt-in.</summary>
    public async Task EnsureChangeTrackingAsync(bool allowEnable, CancellationToken ct = default)
    {
        var table = await RetrieveTableAsync(ct);
        if (table.ChangeTrackingEnabled == true)
        {
            log.WriteLine("Change tracking is already enabled.");
            return;
        }
        if (!allowEnable)
            throw new InvalidOperationException("Change tracking is off for contoso_equipment. It can't be turned off again once enabled: re-run with --enable-change-tracking to confirm.");

        await service.ExecuteAsync(new UpdateEntityRequest
        {
            Entity = new EntityMetadata { LogicalName = Equipment.Table, MetadataId = table.MetadataId, ChangeTrackingEnabled = true },
        }, ct);
        await service.ExecuteAsync(new PublishXmlRequest
        {
            ParameterXml = $"<importexportxml><entities><entity>{Equipment.Table}</entity></entities></importexportxml>",
        }, ct);
        log.WriteLine("Change tracking enabled and published.");
    }

    private async Task<EntityMetadata> RetrieveTableAsync(CancellationToken ct) =>
        ((RetrieveEntityResponse)await service.ExecuteAsync(new RetrieveEntityRequest
        {
            LogicalName = Equipment.Table,
            // We only need Keys and ChangeTrackingEnabled. All is heavier but certain to include the keys; it's a one-off.
            EntityFilters = EntityFilters.All,
            RetrieveAsIfPublished = true,
        }, ct)).EntityMetadata;
}
