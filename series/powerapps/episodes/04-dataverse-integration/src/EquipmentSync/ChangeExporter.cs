using System.ServiceModel;
using System.Text.Json;
using Microsoft.PowerPlatform.Dataverse.Client;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Messages;
using Microsoft.Xrm.Sdk.Query;

namespace EquipmentSync;

/// <summary>
/// What the exporter remembers between runs: the change tracking token, and which asset tag each row id had.
/// A deleted row comes back as an id only (RemovedOrDeletedItem is an EntityReference), so without this map
/// the register would learn that "something" was deleted.
/// </summary>
public sealed class SyncState
{
    public string? DataToken { get; set; }
    public DateTimeOffset? LastRun { get; set; }
    public Dictionary<Guid, string> Tags { get; set; } = new();

    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };
    public static SyncState Load(string path) => File.Exists(path) ? JsonSerializer.Deserialize<SyncState>(File.ReadAllText(path)) ?? new() : new();
    public void Save(string path) => File.WriteAllText(path, JsonSerializer.Serialize(this, Json));
}

public sealed record ExportResult(int NewOrUpdated, int Deleted, int UnknownDeleted, int Pages, bool FullSync);

/// <summary>
/// Sends Equipment changes back to the asset register with RetrieveEntityChanges (change tracking).
/// First run (no token): every row comes back as new. Later runs: only what changed since the token.
/// </summary>
public sealed class ChangeExporter(IOrganizationServiceAsync2 service, int pageSize = 5000)
{
    public static readonly string[] CsvHeader = ["asset_tag", "status", "change"];

    public async Task<ExportResult> ExportAsync(SyncState state, TextWriter csv, bool full = false, CancellationToken ct = default)
    {
        var fullSync = full || state.DataToken is null;
        var request = new RetrieveEntityChangesRequest
        {
            EntityName = Equipment.Table,
            Columns = new ColumnSet(Equipment.AssetTag, Equipment.Status),
            PageInfo = new PagingInfo { Count = pageSize, PageNumber = 1, ReturnTotalRecordCount = false },
            DataVersion = fullSync ? null : state.DataToken,
        };
        if (fullSync) state.Tags.Clear();

        csv.WriteLine(string.Join(",", CsvHeader));
        int changed = 0, deleted = 0, unknown = 0, pages = 0;
        while (true)
        {
            BusinessEntityChanges changes;
            try
            {
                changes = ((RetrieveEntityChangesResponse)await service.ExecuteAsync(request, ct)).EntityChanges;
            }
            catch (FaultException<OrganizationServiceFault> ex) when (!fullSync)
            {
                // Learn: changes are returned if the last token is within 7 days by default
                // (Organization.ExpireChangeTrackingInDays); older tokens throw. Don't guess: ask for a full sync.
                throw new InvalidOperationException(
                    $"Dataverse refused the change tracking token from {state.LastRun:yyyy-MM-dd} ({ex.Detail.Message}). " +
                    "If it's older than the retention period, run again with --full.", ex);
            }
            pages++;

            foreach (var change in changes.Changes)
            {
                switch (change)
                {
                    case NewOrUpdatedItem { NewOrUpdatedEntity: var e }:
                        var tag = e.GetAttributeValue<string>(Equipment.AssetTag);
                        var status = e.GetAttributeValue<OptionSetValue>(Equipment.Status)?.Value;
                        state.Tags[e.Id] = tag;
                        csv.WriteLine(string.Join(",", AssetRegisterCsv.Quote(tag),
                            AssetRegisterCsv.Quote(status is { } s && Equipment.StatusNames.TryGetValue(s, out var n) ? n : ""), "new_or_updated"));
                        changed++;
                        break;
                    case RemovedOrDeletedItem { RemovedItem: var r }:
                        if (state.Tags.Remove(r.Id, out var oldTag))
                        {
                            csv.WriteLine($"{AssetRegisterCsv.Quote(oldTag)},,deleted");
                            deleted++;
                        }
                        else unknown++; // created and deleted between two runs: the register never knew it
                        break;
                }
            }

            if (!changes.MoreRecords)
            {
                // Only move the token forward after every page has been written.
                state.DataToken = changes.DataToken;
                state.LastRun = DateTimeOffset.UtcNow;
                return new ExportResult(changed, deleted, unknown, pages, fullSync);
            }
            request.PageInfo.PageNumber++;
            request.PageInfo.PagingCookie = changes.PagingCookie;
        }
    }
}
