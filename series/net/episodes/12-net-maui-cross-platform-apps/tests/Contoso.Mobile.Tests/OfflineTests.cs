using Contoso.Mobile.Core.Models;
using Contoso.Mobile.Core.Offline;

namespace Contoso.Mobile.Tests;

public class OutboxTests
{
    private static DraftRequest Draft(string title, int minute) =>
        new(Guid.NewGuid(), title, "FIN", 100m, "alex.demo@contoso.com", new DateTime(2026, 11, 21, 10, minute, 0, DateTimeKind.Utc));

    [Fact]
    public async Task Drafts_are_listed_oldest_first_and_survive_a_restart()
    {
        using var dir = new TempDir();
        var first = new FileOutbox(dir.File("outbox.json"));
        var (b, a) = (Draft("second", 5), Draft("first", 1));
        await first.AddAsync(b); await first.AddAsync(a);

        var afterRestart = new FileOutbox(dir.File("outbox.json"));   // a new object over the same file: the app was closed and reopened
        Assert.Equal(["first", "second"], (await afterRestart.ListAsync()).Select(d => d.Title));
        Assert.Equal(a.Key, (await afterRestart.ListAsync())[0].Key);   // the key survives, which is the whole point
    }

    [Fact]
    public async Task The_same_draft_added_twice_is_stored_once_and_remove_and_reject_work()
    {
        using var dir = new TempDir();
        var outbox = new FileOutbox(dir.File("outbox.json"));
        var (keep, drop, bad) = (Draft("keep", 1), Draft("drop", 2), Draft("bad", 3));
        await outbox.AddAsync(keep); await outbox.AddAsync(keep); await outbox.AddAsync(drop); await outbox.AddAsync(bad);
        await outbox.RemoveAsync(drop.Key);
        await outbox.MarkRejectedAsync(bad.Key, "Title: too short");

        var list = await outbox.ListAsync();
        Assert.Equal(["keep", "bad"], list.Select(d => d.Title));
        Assert.False(list[0].NeedsAttention);
        Assert.Equal("Title: too short", list[1].Error);
    }

    [Fact]
    public async Task Fifty_parallel_adds_all_end_up_in_the_file_and_no_temp_file_is_left()
    {
        using var dir = new TempDir();
        var outbox = new FileOutbox(dir.File("outbox.json"));
        await Task.WhenAll(Enumerable.Range(0, 50).Select(i => Task.Run(() => outbox.AddAsync(Draft($"d{i}", i % 59)))));
        Assert.Equal(50, (await outbox.ListAsync()).Count);
        Assert.Empty(Directory.GetFiles(dir.Path, "*.tmp"));
    }

    [Fact]
    public async Task A_damaged_file_is_set_aside_and_the_app_starts_with_an_empty_outbox()
    {
        using var dir = new TempDir();
        await File.WriteAllTextAsync(dir.File("outbox.json"), "[{ this is not json");
        var outbox = new FileOutbox(dir.File("outbox.json"));

        Assert.Empty(await outbox.ListAsync());
        Assert.Single(Directory.GetFiles(dir.Path, "outbox.json.damaged-*"));   // nothing silently destroyed
        await outbox.AddAsync(Draft("after", 1));                               // and it works again
        Assert.Single(await outbox.ListAsync());
    }

    [Fact]
    public async Task The_cache_keeps_the_last_list_and_replaces_it_on_save()
    {
        using var dir = new TempDir();
        var cache = new FileRequestCache(dir.File("cache.json"));
        Assert.Empty(await cache.LoadAsync());
        var item = new RequestItem(1, "Desks", "FIN", 10m, "alex.demo@contoso.com", "Reserved", DateTime.UtcNow);
        await cache.SaveAsync([item, item with { Id = 2 }]);
        await cache.SaveAsync([item with { Id = 3 }]);
        Assert.Equal([3], (await new FileRequestCache(dir.File("cache.json")).LoadAsync()).Select(i => i.Id));
    }
}

public class SyncServiceTests
{
    private static DraftRequest Draft(string title, int minute) =>
        new(Guid.NewGuid(), title, "IT", 500m, "sam.demo@contoso.com", new DateTime(2026, 11, 21, 10, minute, 0, DateTimeKind.Utc));

    private static (SyncService Sync, FileOutbox Outbox, FakeApi Api, FakeConnectivity Net, TempDir Dir) Build()
    {
        var dir = new TempDir(); var outbox = new FileOutbox(dir.File("outbox.json"));
        var (api, net) = (new FakeApi(), new FakeConnectivity());
        return (new SyncService(outbox, api, net), outbox, api, net, dir);
    }

    [Fact]
    public async Task Offline_nothing_is_sent_and_the_outbox_is_untouched()
    {
        var (sync, outbox, api, net, dir) = Build(); using var _ = dir;
        net.IsOnline = false;
        await outbox.AddAsync(Draft("a", 1));
        var report = await sync.FlushAsync();
        Assert.Equal(new SyncReport(0, 0, 1, Skipped: true), report);
        Assert.Empty(api.Submitted);
    }

    [Fact]
    public async Task Online_the_outbox_is_sent_oldest_first_and_emptied()
    {
        var (sync, outbox, api, _, dir) = Build(); using var _ = dir;
        await outbox.AddAsync(Draft("later", 9)); await outbox.AddAsync(Draft("earlier", 2));
        var report = await sync.FlushAsync();
        Assert.Equal(new SyncReport(2, 0, 0, false), report);
        Assert.Equal(["earlier", "later"], api.Submitted.Select(d => d.Title));
        Assert.Empty(await outbox.ListAsync());
    }

    [Fact]
    public async Task When_the_server_is_not_really_there_the_flush_stops_and_keeps_the_rest_in_order()
    {
        var (sync, outbox, api, _, dir) = Build(); using var _ = dir;
        foreach (var (t, m) in new[] { ("one", 1), ("two", 2), ("three", 3) }) await outbox.AddAsync(Draft(t, m));
        api.Script.Enqueue(new SubmitResult(SubmitOutcome.Created));
        api.Script.Enqueue(new SubmitResult(SubmitOutcome.Unavailable, Error: "HTTP 503"));

        var report = await sync.FlushAsync();
        Assert.Equal(new SyncReport(1, 0, 2, false), report);
        Assert.Equal(["one", "two"], api.Submitted.Select(d => d.Title));              // "three" was not even tried
        Assert.Equal(["two", "three"], (await outbox.ListAsync()).Select(d => d.Title));
    }

    [Fact]
    public async Task A_retry_sends_the_same_idempotency_key_as_the_failed_attempt()
    {
        var (sync, outbox, api, _, dir) = Build(); using var _ = dir;
        var draft = Draft("flaky", 1); await outbox.AddAsync(draft);
        api.Script.Enqueue(new SubmitResult(SubmitOutcome.Unavailable));
        await sync.FlushAsync();
        await sync.FlushAsync();
        Assert.Equal([draft.Key, draft.Key], api.Submitted.Select(d => d.Key));
        Assert.Empty(await outbox.ListAsync());
    }

    [Fact]
    public async Task A_rejected_draft_waits_for_the_user_and_is_never_retried_by_itself()
    {
        var (sync, outbox, api, _, dir) = Build(); using var _ = dir;
        await outbox.AddAsync(Draft("bad", 1)); await outbox.AddAsync(Draft("good", 2));
        api.Script.Enqueue(new SubmitResult(SubmitOutcome.Rejected, Error: "Amount: out of range"));

        Assert.Equal(new SyncReport(1, 1, 0, false), await sync.FlushAsync());
        var left = Assert.Single(await outbox.ListAsync());
        Assert.Equal(("bad", "Amount: out of range"), (left.Title, left.Error));

        api.Submitted.Clear();
        await sync.FlushAsync();
        Assert.Empty(api.Submitted);   // not sent again
    }

    [Fact]
    public async Task Two_flushes_at_once_send_each_draft_only_once()
    {
        var (sync, outbox, api, _, dir) = Build(); using var _ = dir;
        api.Delay = TimeSpan.FromMilliseconds(50);
        await outbox.AddAsync(Draft("a", 1)); await outbox.AddAsync(Draft("b", 2));
        await Task.WhenAll(sync.FlushAsync(), sync.FlushAsync(), sync.FlushAsync());   // "back online" + pull-to-refresh + a button
        Assert.Equal(2, api.Submitted.Count);
        Assert.Equal(2, api.Submitted.Select(d => d.Key).Distinct().Count());
    }
}
