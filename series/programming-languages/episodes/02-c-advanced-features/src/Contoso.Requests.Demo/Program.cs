using System.Globalization;
using Contoso.Requests;

// A fixed clock so the output is the same on every run (and in the video).
var clock = new FixedClock(new DateTimeOffset(2026, 11, 21, 10, 0, 0, TimeSpan.Zero));
var store = new InMemoryRequestStore();
var metrics = new ApprovalMetrics();
var service = new ApprovalService(clock, store, metrics);

var alex = EmailAddress.Parse("Alex.Demo@contoso.com");
var sam = EmailAddress.Parse("sam.demo@contoso.com");
var kim = EmailAddress.Parse("kim.demo@contoso.com");

ProjectRequest[] requests =
[
    new() { Code = RequestCode.Parse("PR-2026-0001", null), Title = "  Laptop refresh ", Budget = new(18_000m), RequestedBy = alex },
    new() { Code = RequestCode.Parse("PR-2026-0002", null), Title = "CRM rollout", Budget = Euros.FromThousands(75), RequestedBy = alex },
    new() { Code = RequestCode.Parse("PR-2026-0003", null), Title = "New data platform", Budget = Euros.FromThousands(300), RequestedBy = sam,
            Justification = "Replaces three legacy warehouses." },
];
foreach (var r in requests) store.Save(r);

Console.WriteLine("== Routing (property + relational patterns)");
foreach (var r in requests)
    Console.WriteLine($"  {r.Code}  {r.Budget,12}  {Rules.PriorityFor(r.Budget),-8} -> {Rules.RouteFor(r),-8}  \"{r.Title}\"");

Console.WriteLine("\n== Extension members (C# 14)");
Console.WriteLine($"  requests.TotalBudget          = {requests.TotalBudget}");
Console.WriteLine($"  requests.HighPriority.Count() = {requests.HighPriority.Count()}");
Console.WriteLine($"  clock.Today                   = {clock.Today:yyyy-MM-dd}");
int[] budgetsInThousands = [18, 75, 300];
Console.WriteLine($"  int[].Mean() via span         = {budgetsInThousands.Mean()}");

Console.WriteLine("\n== Workflow");
var code = RequestCode.Parse("PR-2026-0003", null);
Print(service.Submit(code));
Print(service.Approve(code, sam, "Finance"));       // sam requested it
Print(service.Approve(code, kim, "Finance"));       // finance done, board still needed (list pattern)
Print(service.Approve(code, alex, "Board"));        // [Finance, .., Board] -> approved
Console.WriteLine($"  metrics: approved={metrics.Approved}, last decision {metrics.LastDecisionAt:HH:mm}");

Console.WriteLine("\n== Compound assignment (C# 14)");
var tally = new BudgetTally();
foreach (var r in requests) tally += r;
Console.WriteLine($"  {tally.Count} requests, total {tally.Total}, largest {tally.Largest}");

Console.WriteLine("\n== Span parsing without allocations");
var text = "PR-2026-0042,PR-2026-0043,PR-2026-0044".AsSpan();
var before = GC.GetAllocatedBytesForCurrentThread();
var found = 0;
foreach (var range in text.Split(','))
    if (RequestCode.TryParse(text[range], out _)) found++;
var allocated = GC.GetAllocatedBytesForCurrentThread() - before;
Console.WriteLine($"  parsed {found} codes, allocated {allocated.ToString(CultureInfo.InvariantCulture)} bytes");

static void Print(DecisionResult result) => Console.WriteLine(result switch
{
    DecisionResult.Ok(var r) => $"  OK      {r.Code}  {Rules.Describe(r.State)}  approvals=[{string.Join(", ", r.Approvals.Select(a => a.Role))}]",
    DecisionResult.Refused(var reason) => $"  REFUSED {reason}",
    DecisionResult.NotFound(var c) => $"  MISSING {c}",
    _ => "  ?",
});

internal sealed class FixedClock(DateTimeOffset now) : TimeProvider
{
    public override DateTimeOffset GetUtcNow() => now;
}
