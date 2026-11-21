using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Azure.AI.TextAnalytics;
using Azure.Core;
using Azure.Core.Pipeline;

namespace Contoso.SupportTriage.Tests;

/// <summary>
/// A stand-in for the Language REST API, for TESTS ONLY: the real SDK (serialization, paths, headers, auth) runs against it
/// through its own transport. The demo runs the same code against the real service. The "service" here is deliberately
/// dumb (keyword rules); what is tested is how TicketTriage batches, orders and routes, not the quality of the models.
/// </summary>
public sealed class FakeLanguageService : HttpMessageHandler
{
    public sealed record Call(string Kind, string Path, string Query, IReadOnlyList<(string Id, string Text, string? Language)> Documents,
                              string? Authorization, bool HasSubscriptionKey, string RawBody);

    public List<Call> Calls { get; } = [];

    public static (TextAnalyticsClient Client, FakeLanguageService Fake) CreateClient()
    {
        var fake = new FakeLanguageService();
        var options = new TextAnalyticsClientOptions { Transport = new HttpClientTransport(new HttpClient(fake)) };
        var client = new TextAnalyticsClient(new Uri("https://contoso-lang-test.cognitiveservices.azure.com/"), new StaticTokenCredential(), options);
        return (client, fake);
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var raw = await request.Content!.ReadAsStringAsync(ct);
        using var doc = JsonDocument.Parse(raw);
        var kind = doc.RootElement.GetProperty("kind").GetString()!;
        var docs = doc.RootElement.GetProperty("analysisInput").GetProperty("documents").EnumerateArray()
            .Select(d => (Id: d.GetProperty("id").GetString()!, Text: d.GetProperty("text").GetString()!,
                          Language: d.TryGetProperty("language", out var l) ? l.GetString() : null))
            .ToList();
        Calls.Add(new Call(kind, request.RequestUri!.AbsolutePath, request.RequestUri.Query, docs,
            request.Headers.Authorization?.ToString(), request.Headers.Contains("Ocp-Apim-Subscription-Key"), raw));

        var body = kind switch
        {
            "LanguageDetection" => Language(docs),
            "PiiEntityRecognition" => Pii(docs),
            "SentimentAnalysis" => Sentiment(docs),
            _ => throw new InvalidOperationException(kind),
        };
        return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body, Encoding.UTF8, "application/json") };
    }

    private static string Language(List<(string Id, string Text, string? Language)> docs)
    {
        static (string Name, string Iso) Detect(string t) =>
            t.Contains("Boa tarde") ? ("Portuguese", "pt") : t.Contains("Bonjour") ? ("French", "fr") :
            t.Contains("Hola") ? ("Spanish", "es") : ("English", "en");
        var items = docs.Select(d => { var (n, i) = Detect(d.Text); return new { id = d.Id, detectedLanguage = new { name = n, iso6391Name = i, confidenceScore = 0.99 }, warnings = Array.Empty<object>() }; });
        return JsonSerializer.Serialize(new { kind = "LanguageDetectionResults", results = new { documents = items, errors = Array.Empty<object>(), modelVersion = "test" } });
    }

    private static readonly Regex Email = new(@"[\w.]+@[\w.]+\.\w+");
    private static readonly Regex Card = new(@"\b(?:\d{4} ){3}\d{4}\b");

    private static string Pii(List<(string Id, string Text, string? Language)> docs)
    {
        var items = docs.Select(d =>
        {
            var entities = new List<object>();
            var redacted = d.Text;
            foreach (var (rx, cat) in new[] { (Email, "Email"), (Card, "CreditCardNumber") })
                foreach (Match m in rx.Matches(d.Text))
                {
                    entities.Add(new { text = m.Value, category = cat, offset = m.Index, length = m.Length, confidenceScore = 0.9 });
                    redacted = redacted.Replace(m.Value, new string('*', m.Length));
                }
            return new { redactedText = redacted, id = d.Id, entities, warnings = Array.Empty<object>() };
        });
        return JsonSerializer.Serialize(new { kind = "PiiEntityRecognitionResults", results = new { documents = items, errors = Array.Empty<object>(), modelVersion = "test" } });
    }

    private static string Sentiment(List<(string Id, string Text, string? Language)> docs)
    {
        var items = docs.Select(d =>
        {
            var negative = d.Text.Contains("upset") || d.Text.Contains("Terrible") || d.Text.Contains("third time");
            var scores = negative ? new { positive = 0.0, neutral = 0.05, negative = 0.95 } : new { positive = 0.1, neutral = 0.8, negative = 0.1 };
            var label = negative ? "negative" : "neutral";
            return new
            {
                id = d.Id, sentiment = label, confidenceScores = scores, warnings = Array.Empty<object>(),
                sentences = new[] { new { sentiment = label, confidenceScores = scores, offset = 0, length = d.Text.Length, text = d.Text } },
            };
        });
        return JsonSerializer.Serialize(new { kind = "SentimentAnalysisResults", results = new { documents = items, errors = Array.Empty<object>(), modelVersion = "test" } });
    }

    private sealed class StaticTokenCredential : TokenCredential
    {
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken) => new("test-token", DateTimeOffset.UtcNow.AddHours(1));
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) => new(GetToken(requestContext, cancellationToken));
    }
}
