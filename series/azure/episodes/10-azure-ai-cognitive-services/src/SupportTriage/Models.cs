namespace Contoso.SupportTriage;

public sealed record Ticket(string Id, string Text);

public sealed record TriageResult(
    string Id,
    string? Language,
    string? Sentiment,
    double NegativeScore,
    IReadOnlyList<string> PiiCategories,
    string? RedactedText,
    string Route,
    string? Problem);
