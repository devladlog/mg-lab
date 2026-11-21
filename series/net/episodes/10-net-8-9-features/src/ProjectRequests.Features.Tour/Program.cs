using System.Runtime.InteropServices;
using System.Text.Json;
using ProjectRequests.Features;

var requests = SampleData.Requests;
Console.WriteLine($"runtime  : {RuntimeInformation.FrameworkDescription}");
Console.WriteLine($"compiled : {FeatureMatrix.CompiledFor}\n");

Console.WriteLine("== C# 12 on .NET 8 ==");
var report = new RequestReport(requests, TimeProvider.System);
Console.WriteLine($"primary constructor + spread : {string.Join(", ", report.HighThenStandard().Take(4).Select(r => r.Title))} ...");
Console.WriteLine($"alias any type (tuple)       : {report.Total()}");
Console.WriteLine($"default lambda parameter     : {string.Join(" | ", RequestReport.FormatAll([1234.5m, 99m]))}");
Console.WriteLine($"FrozenDictionary             : 'fin' -> {Departments.ByCode["fin"].Name}");
Console.WriteLine($"snake_case JSON              : {JsonSerializer.Serialize(new FeedItem { RequestId = 7, Title = "Backup", Priority = Priority.High }, Feed.SnakeCase)}");
Console.WriteLine($"GroupBy (before CountBy)     : {string.Join(" ", LinqBefore.CountPerDepartment(requests).Select(p => $"{p.Key}={p.Value}"))}");

Console.WriteLine("\n== .NET 9 / C# 13 ==");
#if NET9_0_OR_GREATER
Console.WriteLine($"CountBy                      : {string.Join(" ", Net9Linq.CountPerDepartment(requests).Select(p => $"{p.Key}={p.Value}"))}");
Console.WriteLine($"AggregateBy                  : {string.Join(" ", Net9Linq.BudgetPerDepartment(requests).Select(p => $"{p.Key}={p.Value:N0}"))}");
Console.WriteLine($"Index                        : {string.Join("; ", Net9Linq.Numbered(requests.Take(3)))}");
Console.WriteLine($"params ReadOnlySpan          : {Net9Params.AnyOf(requests[1], Priority.High, Priority.Standard)}");
var numbers = new RequestNumbers();
#pragma warning disable CS9216   // intentional: converting a Lock to object is the point of this line (see README)
Console.WriteLine($"System.Threading.Lock        : {numbers.Next()}, {numbers.Next()}; held in lock(Lock)={RequestNumbers.HeldInsideLockStatement(new Lock())}, in lock(object)={RequestNumbers.HeldInsideLockStatementAsObject(new Lock())}");
#pragma warning restore CS9216
Console.WriteLine($"Guid.CreateVersion7          : {RequestIds.At(DateTimeOffset.UtcNow)} (version {RequestIds.At(DateTimeOffset.UtcNow).Version})");
Console.WriteLine($"Base64Url cursor             : {PageCursor.Encode(1234, requests[0].CreatedAtUtc)}");
Console.WriteLine($"JsonSerializerOptions.Web    : {Net9Misc.ToWebJson(new { SomeValue = 42 })}");
Console.WriteLine($"Task.WhenEach                : {string.Join(" -> ", await Notifier.InCompletionOrderAsync(new[] { Delayed("slow", 150), Delayed("fast", 10), Delayed("medium", 70) }))}");

static async Task<string> Delayed(string name, int ms) { await Task.Delay(ms); return name; }
#else
Console.WriteLine("not compiled into this build: CountBy, AggregateBy, Index, params ReadOnlySpan,");
Console.WriteLine("System.Threading.Lock, Guid.CreateVersion7, Base64Url, Task.WhenEach, OrderedDictionary, ...");
Console.WriteLine("(they need the .NET 9 libraries and C# 13: build for net9.0 or later)");
#endif
