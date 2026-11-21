using System.Text.Json;
using Xunit;

namespace Contoso.SupportTriage.Tests;

public class TicketTriageTests
{
    private static List<Ticket> SampleTickets()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "data", "tickets.json");
        return JsonSerializer.Deserialize<List<Ticket>>(File.ReadAllText(path), new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
    }

    private static async Task<(IReadOnlyList<TriageResult> Results, FakeLanguageService Fake, UsageMeter Meter)> RunAsync(List<Ticket> tickets)
    {
        var (client, fake) = FakeLanguageService.CreateClient();
        var meter = new UsageMeter();
        var results = await new TicketTriage(client, meter).RunAsync(tickets);
        return (results, fake, meter);
    }

    [Fact]
    public async Task Authenticates_with_a_bearer_token_and_never_with_a_key()
    {
        var (_, fake, _) = await RunAsync(SampleTickets());
        Assert.All(fake.Calls, c =>
        {
            Assert.Equal("Bearer test-token", c.Authorization);
            Assert.False(c.HasSubscriptionKey);
            Assert.Equal("/language/:analyze-text", c.Path);
            Assert.Contains("api-version=2023-04-01", c.Query);   // the version infra/rest-check.sh also uses
        });
    }

    [Fact]
    public async Task Respects_the_batch_limits_from_Learn()
    {
        var (_, fake, _) = await RunAsync(SampleTickets());   // 7 tickets
        Assert.Single(fake.Calls, c => c.Kind == "LanguageDetection");       // up to 1000 per request
        var pii = fake.Calls.Where(c => c.Kind == "PiiEntityRecognition").ToList();
        Assert.Equal([5, 2], pii.Select(c => c.Documents.Count));            // PII: 5 per request
        Assert.Single(fake.Calls, c => c.Kind == "SentimentAnalysis");       // sentiment: 10 per request, 7 fit in one
        Assert.All(fake.Calls, c => Assert.True(c.Documents.Count <= (c.Kind == "PiiEntityRecognition" ? 5 : c.Kind == "SentimentAnalysis" ? 10 : 1000)));
    }

    [Fact]
    public async Task Sentiment_only_ever_sees_redacted_text()
    {
        var (_, fake, _) = await RunAsync(SampleTickets());
        var sentimentBodies = fake.Calls.Where(c => c.Kind == "SentimentAnalysis").Select(c => c.RawBody).ToList();
        Assert.NotEmpty(sentimentBodies);
        foreach (var body in sentimentBodies)
        {
            Assert.DoesNotContain("alex.demo@contoso.example", body);
            Assert.DoesNotContain("4111 1111 1111 1111", body);
            Assert.DoesNotContain("riley.demo@contoso.example", body);
        }
        Assert.Contains(fake.Calls.Where(c => c.Kind == "PiiEntityRecognition"), c => c.RawBody.Contains("alex.demo@contoso.example"));
    }

    [Fact]
    public async Task Pii_requests_carry_the_detected_language()
    {
        var (_, fake, _) = await RunAsync(SampleTickets());
        var langs = fake.Calls.Where(c => c.Kind == "PiiEntityRecognition").SelectMany(c => c.Documents).ToDictionary(d => d.Id, d => d.Language);
        Assert.Equal("pt", langs["T-1002"]);
        Assert.Equal("fr", langs["T-1005"]);
        Assert.Equal("es", langs["T-1006"]);
        Assert.Equal("en", langs["T-1001"]);
    }

    [Fact]
    public async Task Routes_follow_the_rules()
    {
        var (results, _, _) = await RunAsync(SampleTickets());
        var byId = results.ToDictionary(r => r.Id);
        Assert.Equal("security-review", byId["T-1004"].Route);     // card number pasted into a ticket
        Assert.Equal("escalate", byId["T-1007"].Route);            // very negative
        Assert.Equal("escalate", byId["T-1001"].Route);
        Assert.Equal("standard-pt", byId["T-1002"].Route);
        Assert.Equal("standard", byId["T-1003"].Route);
        Assert.Contains("Email", byId["T-1001"].PiiCategories);
        Assert.DoesNotContain("alex.demo@contoso.example", byId["T-1001"].RedactedText);
        Assert.All(results, r => Assert.Null(r.Problem));
    }

    [Fact]
    public async Task A_document_over_the_character_limit_is_reported_not_cut_and_not_sent()
    {
        var tickets = SampleTickets();
        tickets.Add(new Ticket("T-LONG", new string('x', Limits.MaxCharactersPerDocument + 1)));
        var (results, fake, _) = await RunAsync(tickets);
        var long1 = results.Single(r => r.Id == "T-LONG");
        Assert.Equal("manual", long1.Route);
        Assert.Contains("5120", long1.Problem);
        Assert.DoesNotContain(fake.Calls, c => c.Documents.Any(d => d.Id == "T-LONG"));
        Assert.Equal(7, results.Count(r => r.Problem is null));
    }

    [Fact]
    public async Task Usage_meter_counts_three_features_per_ticket()
    {
        var (_, _, meter) = await RunAsync(SampleTickets());
        Assert.Equal(7, meter.ByFeature["language"]);   // every ticket is under 1,000 characters: one record each
        Assert.Equal(7, meter.ByFeature["pii"]);
        Assert.Equal(7, meter.ByFeature["sentiment"]);
        Assert.Equal(21, meter.Total);
        Assert.Equal(5000 / 21, meter.RunsPerMonthBeforeFreeTierEnds);
    }
}
