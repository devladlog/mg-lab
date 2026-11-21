using System.Text.Json;
using Azure.AI.TextAnalytics;
using Azure.Identity;
using Contoso.SupportTriage;

// Usage: SupportTriage [--tickets path] [--endpoint https://<name>.cognitiveservices.azure.com/] [--dry-run]
// The endpoint can also come from LANGUAGE_ENDPOINT. There is no key anywhere: the identity of whoever runs this
// (Azure CLI sign-in on the laptop, a managed identity in Azure) needs the "Cognitive Services Language Reader" role.
var options = new Dictionary<string, string>();
for (var i = 0; i < args.Length; i++)
{
    if (!args[i].StartsWith("--")) continue;
    var key = args[i][2..];
    options[key] = key == "dry-run" || i + 1 >= args.Length ? "true" : args[++i];
}

var path = options.GetValueOrDefault("tickets", Path.Combine(AppContext.BaseDirectory, "data", "tickets.json"));
var tickets = JsonSerializer.Deserialize<List<Ticket>>(File.ReadAllText(path), new JsonSerializerOptions(JsonSerializerDefaults.Web))
              ?? throw new InvalidOperationException("no tickets");

var meter = new UsageMeter();
if (options.ContainsKey("dry-run"))
{
    foreach (var t in tickets) { meter.Add("language", t.Text); meter.Add("pii", t.Text); meter.Add("sentiment", t.Text); }
    PrintUsage(meter, "estimate");
    return 0;
}

var endpoint = options.GetValueOrDefault("endpoint") ?? Environment.GetEnvironmentVariable("LANGUAGE_ENDPOINT");
if (string.IsNullOrWhiteSpace(endpoint))
{
    Console.Error.WriteLine("Set --endpoint or LANGUAGE_ENDPOINT (the resource's custom-subdomain endpoint; Entra ID needs it).");
    return 2;
}

var client = new TextAnalyticsClient(new Uri(endpoint), new DefaultAzureCredential());
try
{
    var results = await new TicketTriage(client, meter).RunAsync(tickets);
    foreach (var r in results)
        Console.WriteLine(JsonSerializer.Serialize(r, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    PrintUsage(meter, "billed this run");
    return results.Any(r => r.Problem is not null) ? 1 : 0;
}
catch (Azure.RequestFailedException e)
{
    Console.Error.WriteLine($"HTTP {e.Status} {e.ErrorCode}: {e.Message.Split('\n')[0]}");
    if (e.Status is 401 or 403)
        Console.Error.WriteLine("Hint: is the role 'Cognitive Services Language Reader' assigned on THIS resource to the signed-in identity? Role assignments can take up to five minutes.");
    return 3;
}

static void PrintUsage(UsageMeter meter, string label)
{
    Console.Error.WriteLine(
        $"text records ({label}): {meter.Total} = " + string.Join(", ", meter.ByFeature.Select(kv => $"{kv.Key} {kv.Value}")) +
        $"; that is {meter.FractionOfFreeTier:P1} of the free 5,000 a month, {meter.RunsPerMonthBeforeFreeTierEnds} such runs per month");
}
