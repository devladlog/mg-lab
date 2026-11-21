#if NET9_0_OR_GREATER
using System.Buffers.Text;
using System.Text;

namespace ProjectRequests.Features.Tests;

public class Net9LinqTests
{
    [Fact]
    public void CountBy_and_AggregateBy_give_the_same_answers_as_GroupBy()
    {
        Assert.Equal(LinqBefore.CountPerDepartment(SampleData.Requests), Net9Linq.CountPerDepartment(SampleData.Requests));
        Assert.Equal(LinqBefore.BudgetPerDepartment(SampleData.Requests), Net9Linq.BudgetPerDepartment(SampleData.Requests));
    }

    [Fact]
    public void Index_numbers_the_items_without_a_counter_variable()
    {
        var lines = Net9Linq.Numbered(SampleData.Requests.Take(3)).ToArray();
        Assert.Equal(["1. Laptop refresh", "2. ERP upgrade", "3. Audit tooling"], lines);
    }
}

public class Net9ParamsTests
{
    private static readonly RequestRecord High = SampleData.Requests[1];

    [Fact]
    public void Params_span_and_params_collections_work_like_params_arrays()
    {
        Assert.True(Net9Params.AnyOf(High, Priority.Standard, Priority.High));
        Assert.False(Net9Params.AnyOf(High, Priority.Standard));
        Assert.False(Net9Params.AnyOf(High));                                   // zero arguments: empty span
        Assert.Equal("Laptop refresh, ERP upgrade", Net9Params.JoinTitles(SampleData.Requests[0], SampleData.Requests[1]));
    }

    [Fact]
    public void Params_span_calls_do_not_allocate_an_array()
    {
#if DEBUG
        // Measured here: a Debug build allocates 72 bytes per call for the span version (more than the array's 32),
        // a Release build allocates nothing. Allocation claims are only true for the build you ship.
        Assert.Skip("Allocation behaviour is only meaningful in Release: run dotnet test -c Release");
#endif
        const int Calls = 10_000;
        for (var i = 0; i < 100; i++) { Net9Params.AnyOf(High, Priority.Standard, Priority.High); }   // warm up the JIT

        var before = GC.GetAllocatedBytesForCurrentThread();
        for (var i = 0; i < Calls; i++) { Net9Params.AnyOf(High, Priority.Standard, Priority.High); }
        var spanBytes = GC.GetAllocatedBytesForCurrentThread() - before;

        Assert.True(spanBytes < 1_000, $"params ReadOnlySpan allocated {spanBytes} bytes for {Calls} calls");
    }
}

public class Net9ConcurrencyTests
{
    [Fact]
    public async Task Lock_gives_unique_sequential_numbers_under_contention()
    {
        var numbers = new RequestNumbers();

        var all = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => Task.Run(() =>
            Enumerable.Range(0, 5_000).Select(i => i % 2 == 0 ? numbers.Next() : numbers.NextWithScope()).ToArray(),
            TestContext.Current.CancellationToken)));

        var flat = all.SelectMany(x => x).Order().ToArray();
        Assert.Equal(Enumerable.Range(1, 40_000), flat);        // no duplicates, no gaps
    }

    [Fact]
    public void The_lock_statement_only_uses_the_new_Lock_when_the_expression_is_typed_as_Lock()
    {
        var gate = new Lock();

        Assert.True(RequestNumbers.HeldInsideLockStatement(gate));
#pragma warning disable CS9216   // intentional: the compiler warns about exactly this conversion
        Assert.False(RequestNumbers.HeldInsideLockStatementAsObject(gate));   // same object, but compiled as Monitor.Enter
#pragma warning restore CS9216
    }

    [Fact]
    public async Task WhenEach_hands_over_results_in_the_order_they_finish()
    {
        TaskCompletionSource<string> slow = new(), medium = new(), fast = new();

        var running = Notifier.InCompletionOrderAsync([slow.Task, medium.Task, fast.Task]);
        fast.SetResult("fast");
        await Task.Delay(50, TestContext.Current.CancellationToken);
        medium.SetResult("medium");
        await Task.Delay(50, TestContext.Current.CancellationToken);
        slow.SetResult("slow");

        Assert.Equal(["fast", "medium", "slow"], await running);
    }
}

public class Net9DataTests
{
    [Fact]
    public void Guid_v7_is_version_7_and_sorts_by_creation_time()
    {
        var start = new DateTimeOffset(2026, 11, 21, 10, 0, 0, TimeSpan.Zero);
        var ids = Enumerable.Range(0, 20).Select(i => RequestIds.At(start.AddMinutes(i))).ToArray();

        Assert.All(ids, id => Assert.Equal(7, id.Version));
        Assert.Equal(ids, ids.OrderBy(id => id.ToString(), StringComparer.Ordinal));   // as text, a v7 Guid starts with the timestamp
        Assert.Equal(ids.Distinct().Count(), ids.Length);
    }

    [Fact]
    public void Base64Url_cursor_round_trips_and_needs_no_URL_escaping()
    {
        var created = new DateTime(2026, 1, 5, 9, 0, 0, DateTimeKind.Utc);
        var cursor = PageCursor.Encode(1234, created);

        Assert.Equal((1234, created), PageCursor.Decode(cursor));
        Assert.DoesNotContain('=', cursor);
        Assert.DoesNotContain('+', cursor);
        Assert.DoesNotContain('/', cursor);

        // bytes whose standard Base64 contains + and /: Base64Url swaps them for - and _
        byte[] tricky = [0xFB, 0xEF, 0xFF];
        Assert.Equal("++//", Convert.ToBase64String(tricky));
        Assert.Equal("--__", Base64Url.EncodeToString(tricky));
    }

    [Fact]
    public void OrderedDictionary_keeps_order_and_Insert_puts_a_stage_in_the_middle()
    {
        var workflow = new Workflow();

        Assert.Equal(["Submitted", "Review", "Approved"], workflow.StageNames);
        Assert.Equal(1, workflow.IndexOf("Review"));
        workflow.RemoveFirst();
        Assert.Equal(["Review", "Approved"], workflow.StageNames);
    }

    [Fact]
    public void ReadOnlySet_is_a_live_view_that_cannot_be_changed_through_the_wrapper()
    {
        var workflow = new Workflow();
        var view = workflow.Departments;

        workflow.AddDepartment("OPS");

#pragma warning disable xUnit2017   // Assert.Contains is ambiguous for ReadOnlySet<T> (ISet<T> and IReadOnlySet<T> overloads)
        Assert.True(view.Contains("OPS"));
#pragma warning restore xUnit2017
        Assert.Throws<NotSupportedException>(() => ((ISet<string>)view).Add("HR"));
    }

    [Fact]
    public void JsonSerializerOptions_Web_writes_camelCase_and_reads_any_casing()
    {
        Assert.Equal("""{"someValue":42}""", Net9Misc.ToWebJson(new { SomeValue = 42 }));

        var back = Net9Misc.FromWebJson<FeedItem>("""{"REQUESTID":9,"title":"x"}""")!;
        Assert.Equal(9, back.RequestId);
    }

    [Theory]
    [InlineData("please DROP TABLE users", true)]
    [InlineData("a <SCRIPT>x</SCRIPT>", true)]
    [InlineData("click JavaScript:void(0)", true)]
    [InlineData("quarterly budget review", false)]
    public void SearchValues_of_strings_finds_any_banned_phrase(string text, bool malicious) =>
        Assert.Equal(malicious, Net9Misc.LooksMalicious(text));

    [Fact]
    public void TimeSpan_integer_overload_is_exact()
    {
        Assert.Equal(1_018_320_000L, Net9Misc.Exact(101, 832).Ticks);        // 1 min 41.832 s in 100 ns ticks
        Assert.Equal(TimeSpan.FromMilliseconds(101_832), Net9Misc.Exact(101, 832));
    }
}
#endif
