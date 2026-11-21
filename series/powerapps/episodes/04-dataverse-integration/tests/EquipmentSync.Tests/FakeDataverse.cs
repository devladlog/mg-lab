using System.ServiceModel;
using Microsoft.Crm.Sdk.Messages;
using Microsoft.PowerPlatform.Dataverse.Client;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Messages;
using Microsoft.Xrm.Sdk.Metadata;
using Microsoft.Xrm.Sdk.Query;
using EquipmentSync;

namespace EquipmentSync.Tests;

/// <summary>
/// An in-memory stand-in for the Equipment table, implementing only the messages EquipmentSync sends, with the
/// behaviour Microsoft Learn documents for them:
/// - Upsert by alternate key: update when the key exists (key values in Attributes are ignored), create otherwise
///   (key copied into the row); it needs an Active key index.
/// - ExecuteMultiple: requests run in order, each on its own; with ContinueOnError a fault doesn't stop the rest.
/// - Alternate key index: Pending -> InProgress -> Active (or Failed) over a number of polls.
/// - RetrieveEntityChanges: no token = every current row as new (deleted rows aren't returned); with a token = rows
///   changed since then, new/updated first and deleted last, deleted ones as id only; paged; expired tokens fault.
/// It is NOT Dataverse: no plug-ins, no security, no real metadata. The tests prove EquipmentSync's logic against
/// this documented behaviour; demo.md lists what still needs the lab tenant.
/// </summary>
public sealed class FakeDataverse : IOrganizationServiceAsync2
{
    public Dictionary<Guid, Entity> Rows { get; } = new();
    public List<OrganizationRequest> Requests { get; } = new();
    public bool ChangeTrackingEnabled { get; set; }
    public List<EntityKeyMetadata> Keys { get; } = new();
    public int PollsUntilActive { get; set; } = 2;
    public bool KeyIndexFails { get; set; }
    public int MaxBatchSize { get; set; } = 1000;
    public HashSet<string> ExpiredTokens { get; } = new();
    /// <summary>Simulates a server-side rejection (a plug-in, a business rule) for some rows: return a message to fault.</summary>
    public Func<Entity, string?> Reject { get; set; } = _ => null;

    private long version;
    private readonly List<(long Version, Guid Id, bool Deleted)> changeLog = new();
    private int keyPolls;
    private int guidSeed;

    public string CurrentToken => $"{version}!fake";

    // ---- helpers for tests ---------------------------------------------------------------------------------------

    public Entity Seed(string tag, string name, int status)
    {
        var id = NextId();
        var row = new Entity(Equipment.Table, id) { [Equipment.AssetTag] = tag, [Equipment.Name] = name, [Equipment.Status] = new OptionSetValue(status) };
        Rows[id] = row;
        Touch(id);
        return row;
    }

    public Entity ByTag(string tag) => Rows.Values.Single(r => (string)r[Equipment.AssetTag] == tag);
    public int? StatusOf(string tag) => ByTag(tag).GetAttributeValue<OptionSetValue>(Equipment.Status)?.Value;

    /// <summary>The Equipment Desk app (episode 2) lends a device.</summary>
    public void DeskSetsStatus(string tag, int status) { var r = ByTag(tag); r[Equipment.Status] = new OptionSetValue(status); Touch(r.Id); }

    public void DeleteRow(string tag) { var r = ByTag(tag); Rows.Remove(r.Id); changeLog.Add((++version, r.Id, true)); }

    public void ActivateKeyNow() { Keys.Add(Key(EntityKeyIndexStatus.Active)); }

    private Guid NextId() => new($"00000000-0000-0000-0000-{++guidSeed:D12}");
    private void Touch(Guid id) => changeLog.Add((++version, id, false));

    // ---- the messages ------------------------------------------------------------------------------------------

    public Task<OrganizationResponse> ExecuteAsync(OrganizationRequest request, CancellationToken cancellationToken)
    {
        Requests.Add(request);
        return Task.FromResult(Execute(request, topLevel: true));
    }

    private OrganizationResponse Execute(OrganizationRequest request, bool topLevel) => request switch
    {
        ExecuteMultipleRequest m when topLevel => ExecuteMultiple(m),
        ExecuteMultipleRequest => throw Fault("ExecuteMultiple can't contain ExecuteMultiple."),
        UpsertRequest u => Upsert(u.Target),
        UpdateRequest u => UpdateRow(u.Target),
        RetrieveEntityRequest => Respond(new RetrieveEntityResponse(), "EntityMetadata", TableMetadata()),
        CreateEntityKeyRequest c => CreateKey(c),
        RetrieveEntityKeyRequest k => RetrieveKey(k),
        UpdateEntityRequest u => UpdateTable(u),
        PublishXmlRequest => new PublishXmlResponse(),
        RetrieveEntityChangesRequest c => RetrieveChanges(c),
        _ => throw new NotSupportedException(request.GetType().Name),
    };

    private OrganizationResponse ExecuteMultiple(ExecuteMultipleRequest m)
    {
        if (m.Requests.Count > MaxBatchSize) throw Fault($"The number of requests exceeds the maximum ({MaxBatchSize}).");
        var items = new ExecuteMultipleResponseItemCollection();
        for (var i = 0; i < m.Requests.Count; i++)
        {
            try
            {
                var response = Execute(m.Requests[i], topLevel: false);
                if (m.Settings.ReturnResponses) items.Add(new ExecuteMultipleResponseItem { RequestIndex = i, Response = response });
            }
            catch (FaultException<OrganizationServiceFault> ex)
            {
                items.Add(new ExecuteMultipleResponseItem { RequestIndex = i, Fault = ex.Detail });
                if (!m.Settings.ContinueOnError) break;
            }
        }
        var result = new ExecuteMultipleResponse();
        result.Results["Responses"] = items;
        result.Results["IsFaulted"] = items.Any(x => x.Fault != null);
        return result;
    }

    private OrganizationResponse Upsert(Entity target)
    {
        var tag = target.KeyAttributes.TryGetValue(Equipment.AssetTag, out var k) ? (string)k : throw Fault("No key attributes.");
        if (!Keys.Any(x => x.EntityKeyIndexStatus == EntityKeyIndexStatus.Active && x.KeyAttributes.SequenceEqual([Equipment.AssetTag])))
            throw Fault($"The specified key attributes are not a defined key for the {Equipment.Table} entity (or the index isn't active).");
        if (Reject(target) is { } message) throw Fault(message);

        var existing = Rows.Values.SingleOrDefault(r => (string)r[Equipment.AssetTag] == tag);
        bool created;
        if (existing != null)
        {
            foreach (var a in target.Attributes.Where(a => a.Key != Equipment.AssetTag)) existing[a.Key] = a.Value; // key values ignored
            Touch(existing.Id);
            created = false;
        }
        else
        {
            existing = new Entity(Equipment.Table, NextId());
            foreach (var a in target.Attributes) existing[a.Key] = a.Value;
            if (!existing.Contains(Equipment.AssetTag)) existing[Equipment.AssetTag] = tag; // key copied into the row
            Rows[existing.Id] = existing;
            Touch(existing.Id);
            created = true;
        }
        var response = new UpsertResponse();
        response.Results["RecordCreated"] = created;
        response.Results["Target"] = existing.ToEntityReference();
        return response;
    }

    private OrganizationResponse UpdateRow(Entity target)
    {
        if (!Rows.TryGetValue(target.Id, out var row)) throw Fault($"{Equipment.Table} With Id = {target.Id} Does Not Exist");
        if (Reject(target) is { } message) throw Fault(message);
        foreach (var a in target.Attributes) row[a.Key] = a.Value;
        Touch(row.Id);
        return new UpdateResponse();
    }

    private EntityMetadata TableMetadata()
    {
        var m = new EntityMetadata { LogicalName = Equipment.Table, MetadataId = Guid.Empty, ChangeTrackingEnabled = ChangeTrackingEnabled };
        SetReadOnly(m, nameof(EntityMetadata.Keys), Keys.ToArray());
        return m;
    }

    private static EntityKeyMetadata Key(EntityKeyIndexStatus status)
    {
        var key = new EntityKeyMetadata { LogicalName = Equipment.KeyName, SchemaName = Equipment.KeySchemaName, KeyAttributes = [Equipment.AssetTag] };
        SetReadOnly(key, nameof(EntityKeyMetadata.EntityLogicalName), Equipment.Table); // server-set properties: no public setter
        SetReadOnly(key, nameof(EntityKeyMetadata.EntityKeyIndexStatus), status);
        return key;
    }

    private static void SetReadOnly(object target, string property, object? value) =>
        target.GetType().GetProperty(property)!.SetValue(target, value);

    private OrganizationResponse CreateKey(CreateEntityKeyRequest c)
    {
        if (Keys.Count >= 10) throw Fault("A table can have up to ten alternate keys.");
        if (c.EntityKey.KeyAttributes.Length == 0) throw Fault("A key needs at least one column.");
        Keys.Add(Key(EntityKeyIndexStatus.Pending));
        keyPolls = 0;
        return Respond(new CreateEntityKeyResponse(), "EntityKeyId", Guid.Empty);
    }

    private OrganizationResponse RetrieveKey(RetrieveEntityKeyRequest k)
    {
        var key = Keys.SingleOrDefault(x => x.LogicalName == k.LogicalName && x.EntityLogicalName == k.EntityLogicalName)
            ?? throw Fault($"Key {k.LogicalName} not found.");
        if (key.EntityKeyIndexStatus is EntityKeyIndexStatus.Pending or EntityKeyIndexStatus.InProgress)
        {
            keyPolls++;
            SetReadOnly(key, nameof(EntityKeyMetadata.EntityKeyIndexStatus), KeyIndexFails && keyPolls >= PollsUntilActive ? EntityKeyIndexStatus.Failed
                : keyPolls >= PollsUntilActive ? EntityKeyIndexStatus.Active : EntityKeyIndexStatus.InProgress);
        }
        return Respond(new RetrieveEntityKeyResponse(), "EntityKeyMetadata", Key(key.EntityKeyIndexStatus));
    }

    private OrganizationResponse UpdateTable(UpdateEntityRequest u)
    {
        if (ChangeTrackingEnabled && u.Entity.ChangeTrackingEnabled == false) throw Fault("Change tracking can't be disabled once enabled.");
        if (u.Entity.ChangeTrackingEnabled is { } on) ChangeTrackingEnabled = on;
        return new UpdateEntityResponse();
    }

    private OrganizationResponse RetrieveChanges(RetrieveEntityChangesRequest c)
    {
        if (!ChangeTrackingEnabled) throw Fault("Change tracking is not enabled for this entity.");
        long since = 0;
        if (c.DataVersion is { } token)
        {
            if (ExpiredTokens.Contains(token)) throw Fault("The data version is older than the change tracking retention period.");
            since = long.Parse(token.Split('!')[0]);
        }

        // Latest change per row since the token: new/updated first (by version), then deleted.
        var latest = changeLog.Where(x => x.Version > since).GroupBy(x => x.Id).Select(g => g.OrderBy(x => x.Version).Last()).ToList();
        var items = new List<IChangedItem>();
        foreach (var (_, id, _) in latest.Where(x => !x.Deleted && Rows.ContainsKey(x.Id)).OrderBy(x => x.Version))
        {
            var row = Rows[id];
            var copy = new Entity(Equipment.Table, id);
            foreach (var col in c.Columns.Columns) if (row.Contains(col)) copy[col] = row[col];
            items.Add(new NewOrUpdatedItem(ChangeType.NewOrUpdated, copy));
        }
        if (c.DataVersion != null) // Learn: without a token, deleted objects aren't returned
            foreach (var (_, id, _) in latest.Where(x => x.Deleted).OrderBy(x => x.Version))
                items.Add(new RemovedOrDeletedItem(ChangeType.RemoveOrDeleted, new EntityReference(Equipment.Table, id)));

        var size = c.PageInfo.Count;
        var page = items.Skip((c.PageInfo.PageNumber - 1) * size).Take(size).ToList();
        var more = c.PageInfo.PageNumber * size < items.Count;
        if (c.PageInfo.PageNumber > 1 && c.PageInfo.PagingCookie != $"page{c.PageInfo.PageNumber - 1}") throw Fault("Paging cookie missing or wrong.");
        var changes = new BusinessEntityChanges
        {
            Changes = new BusinessEntityChangesCollection(),
            MoreRecords = more,
            PagingCookie = more ? $"page{c.PageInfo.PageNumber}" : null,
            DataToken = more ? null : CurrentToken,
        };
        foreach (var item in page) changes.Changes.Add(item);
        return Respond(new RetrieveEntityChangesResponse(), "EntityChanges", changes);
    }

    private static T Respond<T>(T response, string key, object value) where T : OrganizationResponse { response.Results[key] = value; return response; }

    private static FaultException<OrganizationServiceFault> Fault(string message) =>
        new(new OrganizationServiceFault { Message = message }, new FaultReason(message));

    // ---- everything else is unused by EquipmentSync -----------------------------------------------------------------

    public Task<Guid> CreateAsync(Entity entity, CancellationToken cancellationToken) => throw new NotSupportedException();
    public Task<Entity> CreateAndReturnAsync(Entity entity, CancellationToken cancellationToken) => throw new NotSupportedException();
    public Task<Entity> RetrieveAsync(string entityName, Guid id, ColumnSet columnSet, CancellationToken cancellationToken) => throw new NotSupportedException();
    public Task UpdateAsync(Entity entity, CancellationToken cancellationToken) => throw new NotSupportedException();
    public Task DeleteAsync(string entityName, Guid id, CancellationToken cancellationToken) => throw new NotSupportedException();
    public Task AssociateAsync(string entityName, Guid entityId, Relationship relationship, EntityReferenceCollection relatedEntities, CancellationToken cancellationToken) => throw new NotSupportedException();
    public Task DisassociateAsync(string entityName, Guid entityId, Relationship relationship, EntityReferenceCollection relatedEntities, CancellationToken cancellationToken) => throw new NotSupportedException();
    public Task<EntityCollection> RetrieveMultipleAsync(QueryBase query, CancellationToken cancellationToken) => throw new NotSupportedException();

    public Task<Guid> CreateAsync(Entity entity) => throw new NotSupportedException();
    public Task<Entity> RetrieveAsync(string entityName, Guid id, ColumnSet columnSet) => throw new NotSupportedException();
    public Task UpdateAsync(Entity entity) => throw new NotSupportedException();
    public Task DeleteAsync(string entityName, Guid id) => throw new NotSupportedException();
    public Task<OrganizationResponse> ExecuteAsync(OrganizationRequest request) => ExecuteAsync(request, CancellationToken.None);
    public Task AssociateAsync(string entityName, Guid entityId, Relationship relationship, EntityReferenceCollection relatedEntities) => throw new NotSupportedException();
    public Task DisassociateAsync(string entityName, Guid entityId, Relationship relationship, EntityReferenceCollection relatedEntities) => throw new NotSupportedException();
    public Task<EntityCollection> RetrieveMultipleAsync(QueryBase query) => throw new NotSupportedException();

    public Guid Create(Entity entity) => throw new NotSupportedException();
    public Entity Retrieve(string entityName, Guid id, ColumnSet columnSet) => throw new NotSupportedException();
    public void Update(Entity entity) => throw new NotSupportedException();
    public void Delete(string entityName, Guid id) => throw new NotSupportedException();
    public OrganizationResponse Execute(OrganizationRequest request) => ExecuteAsync(request, CancellationToken.None).GetAwaiter().GetResult();
    public void Associate(string entityName, Guid entityId, Relationship relationship, EntityReferenceCollection relatedEntities) => throw new NotSupportedException();
    public void Disassociate(string entityName, Guid entityId, Relationship relationship, EntityReferenceCollection relatedEntities) => throw new NotSupportedException();
    public EntityCollection RetrieveMultiple(QueryBase query) => throw new NotSupportedException();
}
