using Microsoft.AspNetCore.OutputCaching;
using ProjectRequests.Perf.Api;
using ProjectRequests.Perf.Api.Caching;
using ProjectRequests.Perf.Api.Data;
using ProjectRequests.Perf.Api.Json;
using ProjectRequests.Perf.Api.Requests;
using ProjectRequests.Perf.Api.Telemetry;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddPerfData(builder.Configuration);
builder.Services.AddSingleton<RequestMetrics>();
builder.Services.AddScoped<SummaryService>();

// JSON: source-generated metadata first in the chain (reflection is switched off in the csproj).
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.TypeInfoResolverChain.Insert(0, AppJsonContext.Default));

// Data cache: HybridCache (stampede protection + tags). No distributed cache registered, so it is in-process only.
// Reflection-based JSON is off, so the cached type brings a serializer built on AppJsonContext.
builder.Services.AddHybridCache().AddSerializer<SummaryDto, SummarySerializer>();

// HTTP cache: output caching, tag-evicted on writes. Default rules: GET/HEAD, 200 only, not for authenticated requests.
builder.Services.AddOutputCache(o => o.AddPolicy(RequestEndpoints.ListPolicy, p => p
    .Expire(TimeSpan.FromSeconds(30))
    .SetVaryByQuery("department", "page", "pageSize")
    .Tag(SummaryService.Tag)));

// Compression: default providers. EnableForHttps stays false: over TLS it is a CRIME/BREACH risk for dynamic content.
builder.Services.AddResponseCompression();

var app = builder.Build();

await using (var scope = app.Services.CreateAsyncScope())
    await Seeder.SeedAsync(scope.ServiceProvider.GetRequiredService<PerfDbContext>(), app.Configuration.GetValue("Perf:SeedCount", 20000));

app.UseResponseCompression();   // before the middleware that writes the body
app.UseOutputCache();

app.MapRequestEndpoints(
    enableSlow: app.Configuration.GetValue("Perf:EnableSlowEndpoint", false),
    listCache: app.Configuration.GetValue("Perf:ListCache", true));

app.Run();

public partial class Program;
