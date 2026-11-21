using EquipmentSync;
using Microsoft.PowerPlatform.Dataverse.Client;

// EquipmentSync: the Contoso asset register <-> the Equipment table in Dataverse (episodes 1-3).
//
//   setup  [--enable-change-tracking]                 alternate key on contoso_assettag, change tracking
//   import <register.csv> [--batch-size N] [--dry-run] upsert devices by asset tag
//   export <state.json> <changes.csv> [--full]         changes since the last run, for the register
//
// Connection: DATAVERSE_CONNECTION_STRING, for example
//   AuthType=ClientSecret;Url=https://<org>.crm4.dynamics.com;ClientId=<app id>;ClientSecret=<secret>
// The app user needs a security role with organization-level Read on Equipment (RetrieveEntityChanges requires it).

return await Cli.RunAsync(args, Console.Out, Console.Error, () =>
{
    var conn = Environment.GetEnvironmentVariable("DATAVERSE_CONNECTION_STRING")
        ?? throw new InvalidOperationException("Set DATAVERSE_CONNECTION_STRING (see the comment at the top of Program.cs).");
    var client = new ServiceClient(conn);
    return client.IsReady ? client : throw new InvalidOperationException("Could not connect: " + client.LastError);
});

public static class Cli
{
    public static async Task<int> RunAsync(string[] args, TextWriter output, TextWriter error, Func<IOrganizationServiceAsync2> connect)
    {
        try
        {
            switch (args.FirstOrDefault())
            {
                case "setup":
                {
                    var setup = new TableSetup(connect(), output);
                    await setup.EnsureAlternateKeyAsync();
                    await setup.EnsureChangeTrackingAsync(args.Contains("--enable-change-tracking"));
                    return 0;
                }
                case "import" when args.Length >= 2:
                {
                    var batchSize = Option(args, "--batch-size") is { } b ? int.Parse(b) : EquipmentImporter.DefaultBatchSize;
                    using var reader = File.OpenText(args[1]);
                    var parsed = AssetRegisterCsv.Parse(reader);
                    foreach (var r in parsed.Rejected) error.WriteLine($"line {r.Line} {r.AssetTag}: rejected, {r.Message}");

                    if (args.Contains("--dry-run"))
                    {
                        // Shows exactly what would be sent, without connecting.
                        foreach (var row in parsed.Rows)
                        {
                            var e = EquipmentImporter.ToEntity(row);
                            output.WriteLine($"Upsert {e.LogicalName}({Equipment.AssetTag}='{row.AssetTag}') " +
                                string.Join(", ", e.Attributes.Select(a => $"{a.Key}={Show(a.Value)}")));
                        }
                        output.WriteLine($"{parsed.Rows.Count} rows to upsert in {(parsed.Rows.Count + batchSize - 1) / batchSize} batches of up to {batchSize}, {parsed.Rejected.Count} rejected.");
                        return parsed.Rejected.Count == 0 ? 0 : 2;
                    }

                    var report = await new EquipmentImporter(connect(), batchSize).ImportAsync(parsed.Rows);
                    foreach (var r in report.Results.Where(r => r.Message != null)) error.WriteLine($"line {r.Line} {r.AssetTag}: {r.Outcome}, {r.Message}");
                    var all = report.Results.Concat(parsed.Rejected).ToList();
                    output.WriteLine(new ImportReport(all, report.RequestsSent));
                    return all.Any(r => r.Outcome is RowOutcome.Failed or RowOutcome.Rejected) ? 2 : 0;
                }
                case "export" when args.Length >= 3:
                {
                    var state = SyncState.Load(args[1]);
                    await using var csv = File.CreateText(args[2]);
                    var result = await new ChangeExporter(connect()).ExportAsync(state, csv, args.Contains("--full"));
                    state.Save(args[1]); // only after the CSV is complete
                    output.WriteLine($"{(result.FullSync ? "full sync" : "changes")}: {result.NewOrUpdated} new or updated, " +
                                     $"{result.Deleted} deleted ({result.UnknownDeleted} unknown), {result.Pages} page(s)");
                    return 0;
                }
                default:
                    error.WriteLine("usage: EquipmentSync setup [--enable-change-tracking] | import <register.csv> [--batch-size N] [--dry-run] | export <state.json> <changes.csv> [--full]");
                    return 1;
            }
        }
        catch (Exception ex) when (ex is InvalidOperationException or FormatException or TimeoutException or ArgumentOutOfRangeException or IOException)
        {
            error.WriteLine("error: " + ex.Message);
            return 1;
        }
    }

    private static string? Option(string[] args, string name)
    {
        var i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    private static string Show(object? value) => value switch
    {
        null => "null",
        Microsoft.Xrm.Sdk.OptionSetValue o => o.Value.ToString(),
        DateTime d => d.ToString("yyyy-MM-dd"),
        _ => value.ToString() ?? "",
    };
}
