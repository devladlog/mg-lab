using System.Text.Json;
using System.Text.Json.Serialization;
using BenchmarkDotNet.Attributes;
using ProjectRequests.Perf.Api.Data;
using ProjectRequests.Perf.Api.Json;
using ProjectRequests.Perf.Api.Requests;

namespace ProjectRequests.Perf.Benchmarks;

/// <summary>Serialising one page of 100 DTOs: reflection-based metadata vs the source-generated context. Same JSON out.</summary>
[MemoryDiagnoser]
public class JsonBenchmarks
{
    private static readonly JsonSerializerOptions Reflection = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() },
        TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver(),
    };

    private readonly List<RequestDto> _page = Enumerable.Range(1, 100)
        .Select(i => new RequestDto(i, $"Project {i:00000}", 1234.50m * i, "FIN", $"Requester {i % 400:000}",
            i % 2 == 0 ? Priority.High : Priority.Standard, (RequestStatus)(i % 3),
            new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddMinutes(i)))
        .ToList();

    [Benchmark(Baseline = true)]
    public string Reflection_based() => JsonSerializer.Serialize(_page, Reflection);

    [Benchmark]
    public string Source_generated() => JsonSerializer.Serialize(_page, AppJsonContext.Default.ListRequestDto);

    [Benchmark]
    public byte[] Source_generated_utf8() => JsonSerializer.SerializeToUtf8Bytes(_page, AppJsonContext.Default.ListRequestDto);
}
