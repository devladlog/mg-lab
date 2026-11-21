using Microsoft.PowerPlatform.Dataverse.Client;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Messages;

namespace EquipmentSync;

public sealed record ImportReport(IReadOnlyList<RowResult> Results, int RequestsSent)
{
    public int Count(RowOutcome outcome) => Results.Count(r => r.Outcome == outcome);
    public override string ToString() =>
        $"created {Count(RowOutcome.Created)}, updated {Count(RowOutcome.Updated)}, failed {Count(RowOutcome.Failed)}, " +
        $"rejected {Count(RowOutcome.Rejected)} ({RequestsSent} ExecuteMultiple requests)";
}

/// <summary>
/// Upserts asset-register rows into Equipment, identified by the alternate key contoso_assettag.
/// ExecuteMultiple with ContinueOnError: each upsert is its own transaction, so one bad row doesn't sink the batch
/// (UpsertMultiple on a standard table rolls back the whole request on any error - Learn: bulk operations).
/// </summary>
public sealed class EquipmentImporter(IOrganizationServiceAsync2 service, int batchSize = EquipmentImporter.DefaultBatchSize)
{
    // Learn (service protection limits): "start with a small batch size of 10"; ExecuteMultiple allows up to 1,000.
    public const int DefaultBatchSize = 10;
    public const int MaxBatchSize = 1000;

    private readonly int batchSize = batchSize is >= 1 and <= MaxBatchSize
        ? batchSize : throw new ArgumentOutOfRangeException(nameof(batchSize), $"batch size must be 1..{MaxBatchSize}");

    public async Task<ImportReport> ImportAsync(IReadOnlyList<AssetRow> rows, CancellationToken ct = default)
    {
        var results = new Dictionary<int, RowResult>();
        var needsStatus = new List<(AssetRow Row, Guid Id)>();
        var requestsSent = 0;

        // Pass 1: upsert every row.
        foreach (var batch in rows.Chunk(batchSize))
        {
            var responses = await ExecuteBatchAsync(batch.Select(r => (OrganizationRequest)new UpsertRequest { Target = ToEntity(r) }), ct);
            requestsSent++;
            for (var i = 0; i < batch.Length; i++)
            {
                var row = batch[i];
                if (!responses.TryGetValue(i, out var item)) { results[row.Line] = new(row.Line, row.AssetTag, RowOutcome.Failed, "no response returned"); continue; }
                if (item.Fault != null) { results[row.Line] = new(row.Line, row.AssetTag, RowOutcome.Failed, item.Fault.Message); continue; }
                var upsert = (UpsertResponse)item.Response;
                results[row.Line] = new(row.Line, row.AssetTag, upsert.RecordCreated ? RowOutcome.Created : RowOutcome.Updated);
                if (upsert.RecordCreated && StatusFromRegister(row) is null) needsStatus.Add((row, upsert.Target.Id));
            }
        }

        // Pass 2: Upsert can't say "set this column only when you create the row". New devices still need a status,
        // but sending Available on every run would put laptops that are on loan back to Available each night.
        foreach (var batch in needsStatus.Chunk(batchSize))
        {
            var responses = await ExecuteBatchAsync(batch.Select(x => (OrganizationRequest)new UpdateRequest
            {
                Target = new Entity(Equipment.Table, x.Id) { [Equipment.Status] = new OptionSetValue(Equipment.Available) },
            }), ct);
            requestsSent++;
            for (var i = 0; i < batch.Length; i++)
                if (responses.TryGetValue(i, out var item) && item.Fault != null)
                    results[batch[i].Row.Line] = results[batch[i].Row.Line] with { Message = "created, but status not set: " + item.Fault.Message };
        }

        return new ImportReport(rows.Select(r => results[r.Line]).ToList(), requestsSent);
    }

    /// <summary>The Equipment row for an upsert. The key goes in KeyAttributes, not in Attributes (Learn: Upsert guidance).</summary>
    internal static Entity ToEntity(AssetRow row)
    {
        var entity = new Entity(Equipment.Table, Equipment.AssetTag, row.AssetTag)
        {
            [Equipment.Name] = row.Name,
            [Equipment.Category] = new OptionSetValue(Equipment.Categories[row.Category]),
            [Equipment.SerialNumber] = row.SerialNumber,                                                   // null clears it
            [Equipment.PurchaseDate] = row.PurchaseDate?.ToDateTime(TimeOnly.MinValue, DateTimeKind.Unspecified), // date-only column
        };
        if (StatusFromRegister(row) is { } status) entity[Equipment.Status] = new OptionSetValue(status);
        return entity;
    }

    /// <summary>
    /// The register owns "in repair" and "retired". "In service" says nothing about Available vs On loan: that's the
    /// Equipment Desk's job (episode 2), so the import leaves the status alone.
    /// </summary>
    internal static int? StatusFromRegister(AssetRow row) => row.RegisterStatus switch
    {
        "in_repair" => Equipment.InRepair,
        "retired" => Equipment.Retired,
        _ => null,
    };

    private async Task<Dictionary<int, ExecuteMultipleResponseItem>> ExecuteBatchAsync(IEnumerable<OrganizationRequest> requests, CancellationToken ct)
    {
        var request = new ExecuteMultipleRequest
        {
            Settings = new ExecuteMultipleSettings { ContinueOnError = true, ReturnResponses = true },
            Requests = new OrganizationRequestCollection(),
        };
        request.Requests.AddRange(requests);
        var response = (ExecuteMultipleResponse)await service.ExecuteAsync(request, ct);
        return response.Responses.ToDictionary(r => r.RequestIndex);
    }
}
