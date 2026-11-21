using System.Buffers;
using System.Text.Json;
using Microsoft.Extensions.Caching.Hybrid;
using ProjectRequests.Perf.Api.Json;
using ProjectRequests.Perf.Api.Requests;

namespace ProjectRequests.Perf.Api.Caching;

/// <summary>
/// HybridCache serialises every value it stores, even with no distributed cache. By default it uses System.Text.Json
/// with reflection, which this app has switched off, so the type needs a serializer built on the source-generated context
/// (the same advice Learn gives for Native AOT).
/// </summary>
public sealed class SummarySerializer : IHybridCacheSerializer<SummaryDto>
{
    public SummaryDto Deserialize(ReadOnlySequence<byte> source)
    {
        var reader = new Utf8JsonReader(source);
        return JsonSerializer.Deserialize(ref reader, AppJsonContext.Default.SummaryDto)
            ?? throw new JsonException("Cached summary was null.");
    }

    public void Serialize(SummaryDto value, IBufferWriter<byte> target)
    {
        using var writer = new Utf8JsonWriter(target);
        JsonSerializer.Serialize(writer, value, AppJsonContext.Default.SummaryDto);
    }
}
