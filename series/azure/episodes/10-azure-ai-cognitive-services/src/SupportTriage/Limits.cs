using System.Globalization;

namespace Contoso.SupportTriage;

/// <summary>Limits of the synchronous Azure Language preconfigured features (Learn: "Service limits for Azure Language").</summary>
public static class Limits
{
    public const int LanguageDetectionMaxDocuments = 1000;
    public const int PiiMaxDocuments = 5;
    public const int SentimentMaxDocuments = 10;

    /// <summary>Characters per document, measured as StringInfo.LengthInTextElements.</summary>
    public const int MaxCharactersPerDocument = 5120;

    /// <summary>Pricing and the free tier count text records of 1,000 characters.</summary>
    public const int CharactersPerTextRecord = 1000;

    /// <summary>F0: 5,000 text records per month.</summary>
    public const int FreeTierTextRecordsPerMonth = 5000;

    public static int LengthInTextElements(string text) => new StringInfo(text).LengthInTextElements;

    public static int TextRecords(string text)
    {
        var length = LengthInTextElements(text);
        return Math.Max(1, (length + CharactersPerTextRecord - 1) / CharactersPerTextRecord);
    }

    public static IEnumerable<IReadOnlyList<T>> Chunk<T>(IEnumerable<T> items, int size) =>
        items.Chunk(size).Select(c => (IReadOnlyList<T>)c);
}
