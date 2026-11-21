using Azure;
using Azure.AI.TextAnalytics;

namespace Contoso.SupportTriage;

/// <summary>
/// Language detection, then PII redaction (the only call that sees the raw text), then sentiment on the REDACTED text.
/// Batches follow the documented limits; documents over the character limit are reported, never silently cut.
/// </summary>
public sealed class TicketTriage(TextAnalyticsClient client, UsageMeter meter)
{
    public async Task<IReadOnlyList<TriageResult>> RunAsync(IReadOnlyList<Ticket> tickets, CancellationToken ct = default)
    {
        var results = new Dictionary<string, Work>();
        foreach (var t in tickets)
        {
            var w = new Work(t);
            if (Limits.LengthInTextElements(t.Text) > Limits.MaxCharactersPerDocument)
                w.Problem = $"longer than {Limits.MaxCharactersPerDocument} characters: split it before sending";
            results[t.Id] = w;
        }

        var ok = results.Values.Where(w => w.Problem is null).ToList();

        // 1. language (up to 1000 documents per request)
        foreach (var chunk in Limits.Chunk(ok, Limits.LanguageDetectionMaxDocuments))
        {
            var inputs = chunk.Select(w => new DetectLanguageInput(w.Ticket.Id, w.Ticket.Text));
            foreach (var w in chunk) meter.Add("language", w.Ticket.Text);
            var response = await client.DetectLanguageBatchAsync(inputs, cancellationToken: ct);
            foreach (var r in response.Value)
            {
                var w = results[r.Id];
                if (r.HasError) { w.Problem = $"language: {r.Error.ErrorCode}"; continue; }
                w.LanguageIso = r.PrimaryLanguage.Iso6391Name;
            }
        }

        // 2. PII (5 documents per request), with the detected language as the document language
        foreach (var chunk in Limits.Chunk(ok.Where(w => w.Problem is null), Limits.PiiMaxDocuments))
        {
            var inputs = chunk.Select(w => new TextDocumentInput(w.Ticket.Id, w.Ticket.Text) { Language = w.LanguageIso });
            foreach (var w in chunk) meter.Add("pii", w.Ticket.Text);
            var response = await client.RecognizePiiEntitiesBatchAsync(inputs, cancellationToken: ct);
            foreach (var r in response.Value)
            {
                var w = results[r.Id];
                if (r.HasError) { w.Problem = $"pii: {r.Error.ErrorCode}"; continue; }
                w.Redacted = r.Entities.RedactedText;
                w.PiiCategories = r.Entities.Select(e => e.Category.ToString()).Distinct().ToList();
            }
        }

        // 3. sentiment (10 documents per request) on the redacted text only
        foreach (var chunk in Limits.Chunk(ok.Where(w => w.Problem is null), Limits.SentimentMaxDocuments))
        {
            var inputs = chunk.Select(w => new TextDocumentInput(w.Ticket.Id, w.Redacted!) { Language = w.LanguageIso });
            foreach (var w in chunk) meter.Add("sentiment", w.Redacted!);
            var response = await client.AnalyzeSentimentBatchAsync(inputs, cancellationToken: ct);
            foreach (var r in response.Value)
            {
                var w = results[r.Id];
                if (r.HasError) { w.Problem = $"sentiment: {r.Error.ErrorCode}"; continue; }
                w.Sentiment = r.DocumentSentiment.Sentiment.ToString().ToLowerInvariant();
                w.Negative = r.DocumentSentiment.ConfidenceScores.Negative;
            }
        }

        return tickets.Select(t => results[t.Id].ToResult()).ToList();
    }

    private sealed class Work(Ticket ticket)
    {
        public Ticket Ticket { get; } = ticket;
        public string? LanguageIso, Sentiment, Redacted, Problem;
        public double Negative;
        public IReadOnlyList<string> PiiCategories { get; set; } = [];

        public TriageResult ToResult() => new(
            Ticket.Id, LanguageIso, Sentiment, Negative, PiiCategories, Redacted,
            Problem is null ? Router.Route(Sentiment, Negative, PiiCategories, LanguageIso) : "manual",
            Problem);
    }
}
