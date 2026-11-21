using System.Globalization;
using System.Text.Json;
using Contoso.Approvals.Patterns;
using Contoso.Approvals.Patterns.Cli;
using Contoso.Approvals.Patterns.Approvers;
using Contoso.Approvals.Patterns.Events;
using Contoso.Approvals.Patterns.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Options;

// Usage (from the episode folder):
//   dotnet run --project src/Contoso.Approvals.Patterns.Cli [-- samples/requests.json]
//   ... -- --Policy:BoardThreshold=10000            options validation fails at startup
//   ... -- --Demo:CaptiveAudit=true                 the lifetime mistake, Production (default) environment
//   ... -- --Demo:CaptiveAudit=true --environment Development
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

var builder = Host.CreateApplicationBuilder(new HostApplicationBuilderSettings
{
    Args = args,
    ContentRootPath = AppContext.BaseDirectory, // appsettings.json next to the .exe; samples/ stay relative to the current folder
});

builder.Services.AddApprovalCore(builder.Configuration);
var captiveMistake = builder.Configuration.GetValue<bool>("Demo:CaptiveAudit");
if (captiveMistake)
{
    builder.Services.AddRequestObserversWithCaptiveAudit(); // wrong on purpose, see Mistakes.cs
}
else
{
    builder.Services.AddRequestObservers();
}

IHost host;
try
{
    host = builder.Build();
    await host.StartAsync(); // runs ValidateOnStart
}
catch (Exception ex) when (ex is OptionsValidationException or AggregateException or InvalidOperationException)
{
    Console.WriteLine($"Startup failed in {builder.Environment.EnvironmentName}: {ex.GetType().Name}");
    Console.WriteLine($"  {ex.Message}");
    return 1;
}

var policy = host.Services.GetRequiredService<IOptions<ApprovalPolicyOptions>>().Value;
var catalog = host.Services.GetRequiredService<RouteCatalog>();
Console.WriteLine($"Contoso approvals | environment: {builder.Environment.EnvironmentName} | " +
                  $"High >= {policy.HighThreshold:N0} EUR | Board >= {policy.BoardThreshold:N0} EUR");
Console.WriteLine($"routes (strategy): {string.Join(", ", catalog.Keys)}");

var file = args.FirstOrDefault(a => !a.StartsWith("--", StringComparison.Ordinal)) ?? "samples/requests.json";
await using var json = File.OpenRead(file);
var batches = await JsonSerializer.DeserializeAsync<ProjectRequest[][]>(json, JsonSerializerOptions.Web) ?? [];

var batchNumber = 0;
foreach (var batch in batches)
{
    batchNumber++;
    Console.WriteLine();
    Console.WriteLine($"Batch {batchNumber} (new DI scope)");
    await using var scope = host.Services.CreateAsyncScope();
    var service = scope.ServiceProvider.GetRequiredService<ApprovalService>();

    foreach (var request in batch)
    {
        var result = await service.SubmitAsync(request);
        var steps = string.Join(" -> ", result.Routed.Steps.Select(s => $"{s.Role}: {s.Approver}"));
        Console.WriteLine($"  {request.Code}  {request.Title,-22} {request.Budget,12:N2} EUR  " +
                          $"{result.Routed.Route,-8}  {steps,-42} {result.Routed.DueInDays,2} days");
        foreach (var warning in result.Routed.Warnings)
        {
            Console.WriteLine($"    ! {warning}");
        }

        foreach (var failure in result.ObserverFailures)
        {
            Console.WriteLine($"    x observer failed: {failure}");
        }
    }

    var audit = scope.ServiceProvider.GetRequiredService<AuditTrail>();
    var verdict = audit.Entries.Count == batch.Length ? "ok" : $"MISSING, expected {batch.Length}";
    Console.WriteLine($"  audit trail (scoped): {audit.Entries.Count} entries  [{verdict}]");
}

var stats = host.Services.GetRequiredService<DirectoryStats>();
var outbox = host.Services.GetRequiredService<IOptions<OutboxOptions>>().Value.Folder;
var tally = host.Services.GetRequiredService<BudgetTally>().Snapshot();
Console.WriteLine();
Console.WriteLine($"directory (decorators): {stats.Lookups} lookups, {stats.FileReads} file reads, {stats.ServedFromCache} from cache");
Console.WriteLine($"outbox (observer): {Directory.GetFiles(outbox, "PR-*.txt").Length} notification files in ./{outbox}");
Console.WriteLine($"tally (observer): {string.Join(" | ", tally.Select(t => $"{t.Route} {t.Count} = {t.Total:N2} EUR"))}");

await host.StopAsync();
return 0;
