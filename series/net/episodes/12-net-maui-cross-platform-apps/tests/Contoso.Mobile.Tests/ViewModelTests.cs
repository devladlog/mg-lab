using System.Globalization;
using System.Windows.Input;
using Contoso.Mobile.Core.Models;
using Contoso.Mobile.Core.Offline;
using Contoso.Mobile.Core.ViewModels;
using Microsoft.Extensions.Time.Testing;

namespace Contoso.Mobile.Tests;

public class NewRequestViewModelTests : IDisposable
{
    private readonly TempDir _dir = new();
    private readonly FakeApi _api = new();
    private readonly FakeConnectivity _net = new();
    private readonly FileOutbox _outbox;
    private readonly NewRequestViewModel _vm;

    public NewRequestViewModelTests()
    {
        _outbox = new FileOutbox(_dir.File("outbox.json"));
        _vm = new NewRequestViewModel(_outbox, new SyncService(_outbox, _api, _net), new FakeTimeProvider(new DateTimeOffset(2026, 11, 21, 10, 0, 0, TimeSpan.Zero)))
        { Culture = CultureInfo.InvariantCulture };
    }

    public void Dispose() => _dir.Dispose();

    private void Fill(string title = "Standing desks", string? dept = "FIN", string amount = "12000", string email = "alex.demo@contoso.com") =>
        (_vm.Title, _vm.DepartmentCode, _vm.AmountText, _vm.RequestedBy) = (title, dept, amount, email);

    [Fact]
    public async Task Mistakes_are_listed_and_nothing_is_stored_or_sent()
    {
        Fill(title: "x", dept: null, amount: "abc", email: "nope");
        await _vm.SubmitCommand.ExecuteAsync(null);
        Assert.Contains("Title:", _vm.Errors); Assert.Contains("Department:", _vm.Errors);
        Assert.Contains("Amount:", _vm.Errors); Assert.Contains("Requested by:", _vm.Errors);
        Assert.Empty(await _outbox.ListAsync()); Assert.Empty(_api.Submitted);
    }

    [Theory]
    [InlineData("0")] [InlineData("10000001")] [InlineData("")]
    public async Task The_amount_must_be_in_the_servers_range(string amount)
    {
        Fill(amount: amount);
        await _vm.SubmitCommand.ExecuteAsync(null);
        Assert.Contains("Amount:", _vm.Errors);
    }

    [Fact]
    public async Task Online_the_request_is_stored_then_sent_and_the_form_closes()
    {
        Fill(); string? closed = null; _vm.Submitted += (_, m) => closed = m;
        await _vm.SubmitCommand.ExecuteAsync(null);

        Assert.Equal("Sent.", _vm.Result); Assert.Equal("Sent.", closed);
        Assert.Equal(("Standing desks", "FIN", 12_000m), _api.Submitted.Select(d => (d.Title, d.DepartmentCode, d.Amount)).Single());
        Assert.Empty(await _outbox.ListAsync());
    }

    [Fact]
    public async Task Offline_the_request_is_kept_on_the_device_and_the_user_is_told()
    {
        _net.IsOnline = false; Fill(); string? closed = null; _vm.Submitted += (_, m) => closed = m;
        await _vm.SubmitCommand.ExecuteAsync(null);

        Assert.Contains("will be sent when you are back online", _vm.Result); Assert.NotNull(closed);
        Assert.Empty(_api.Submitted);
        var draft = Assert.Single(await _outbox.ListAsync());
        Assert.Equal(("Standing desks", 12_000m, new DateTime(2026, 11, 21, 10, 0, 0, DateTimeKind.Utc)), (draft.Title, draft.Amount, draft.QueuedAtUtc));
    }

    [Fact]
    public async Task Online_but_the_server_is_down_the_draft_stays_and_the_message_says_so()
    {
        Fill(); _api.Script.Enqueue(new SubmitResult(SubmitOutcome.Unavailable));
        await _vm.SubmitCommand.ExecuteAsync(null);
        Assert.Contains("server is not reachable", _vm.Result);
        Assert.Single(await _outbox.ListAsync());
    }

    [Fact]
    public async Task A_refusal_from_the_server_is_shown_and_the_form_stays_open()
    {
        Fill(); bool closed = false; _vm.Submitted += (_, _) => closed = true;
        _api.Script.Enqueue(new SubmitResult(SubmitOutcome.Rejected, Error: "Idempotency-Key already used."));
        await _vm.SubmitCommand.ExecuteAsync(null);
        Assert.Equal("The server refused it: Idempotency-Key already used.", _vm.Result);
        Assert.False(closed);
    }

    [Fact]
    public async Task A_phone_set_to_a_comma_decimal_culture_can_type_12000_50()
    {
        _vm.Culture = new CultureInfo("en-US") { NumberFormat = { NumberDecimalSeparator = ",", NumberGroupSeparator = " " } };
        Fill(amount: "12000,50");
        await _vm.SubmitCommand.ExecuteAsync(null);
        Assert.Equal(12_000.50m, _api.Submitted.Single().Amount);
    }

    [Fact]
    public async Task While_a_submit_is_running_the_command_says_it_can_not_run_so_the_button_is_disabled()
    {
        _api.Delay = TimeSpan.FromMilliseconds(150); Fill();
        ICommand tap = _vm.SubmitCommand;                 // a Button talks to the command through ICommand
        Assert.True(tap.CanExecute(null));
        tap.Execute(null);
        Assert.False(tap.CanExecute(null));               // CanExecute turns false: MAUI disables the Button and ignores taps
        await _vm.SubmitCommand.ExecutionTask!;
        Assert.True(tap.CanExecute(null));
    }

    [Fact]
    public async Task Calling_ExecuteAsync_twice_from_code_is_not_guarded_the_guard_is_CanExecute()
    {
        _api.Delay = TimeSpan.FromMilliseconds(100); Fill();
        await Task.WhenAll(_vm.SubmitCommand.ExecuteAsync(null), _vm.SubmitCommand.ExecuteAsync(null));
        Assert.Equal(2, _api.Submitted.Count);            // what we saw: two drafts. The guard is CanExecute (the Button), not the command itself.
    }
}

public class RequestListViewModelTests : IDisposable
{
    private readonly TempDir _dir = new();
    private readonly FakeApi _api = new();
    private readonly FakeConnectivity _net = new();
    private readonly FileOutbox _outbox;
    private readonly FileRequestCache _cache;
    private readonly RequestListViewModel _vm;

    public RequestListViewModelTests()
    {
        (_outbox, _cache) = (new FileOutbox(_dir.File("outbox.json")), new FileRequestCache(_dir.File("cache.json")));
        _vm = new RequestListViewModel(_api, _cache, _outbox, new SyncService(_outbox, _api, _net), _net, new InlineUi());
    }

    public void Dispose() => _dir.Dispose();

    private static RequestItem Item(int id, string title, string state = "Reserved") =>
        new(id, title, "FIN", 12_000m, "alex.demo@contoso.com", state, DateTime.UtcNow);

    private static DraftRequest Draft(string title) => new(Guid.NewGuid(), title, "IT", 900m, "sam.demo@contoso.com", DateTime.UtcNow);

    [Fact]
    public async Task Online_the_list_is_read_cached_and_newest_first_with_readable_badges()
    {
        _api.Server.AddRange([Item(1, "Old", "Declined"), Item(2, "New", "Pending")]);
        await _vm.RefreshCommand.ExecuteAsync(null);

        Assert.Equal(["New", "Old"], _vm.Rows.Select(r => r.Title));
        Assert.Equal(["Budget check pending", "Budget declined"], _vm.Rows.Select(r => r.Badge));
        Assert.Equal("Up to date.", _vm.Status);
        Assert.Equal(2, (await _cache.LoadAsync()).Count);
        Assert.False(_vm.IsBusy);
    }

    [Fact]
    public async Task Offline_the_saved_list_is_shown_with_the_waiting_drafts_on_top()
    {
        await _cache.SaveAsync([Item(1, "Saved earlier")]);
        await _outbox.AddAsync(Draft("Written offline"));
        _net.IsOnline = false;
        await _vm.RefreshCommand.ExecuteAsync(null);

        Assert.Equal(["Written offline", "Saved earlier"], _vm.Rows.Select(r => r.Title));
        Assert.Equal(("Waiting to be sent", true), (_vm.Rows[0].Badge, _vm.Rows[0].IsDraft));
        Assert.StartsWith("Offline.", _vm.Status);
        Assert.Empty(_api.Submitted);
    }

    [Fact]
    public async Task Online_but_unreachable_the_saved_list_is_shown_instead_of_an_error()
    {
        await _cache.SaveAsync([Item(1, "Saved earlier")]);
        _api.ListFails = true;
        await _vm.RefreshCommand.ExecuteAsync(null);
        Assert.Equal(["Saved earlier"], _vm.Rows.Select(r => r.Title));
        Assert.StartsWith("Server not reachable.", _vm.Status);
    }

    [Fact]
    public async Task A_refresh_sends_waiting_drafts_first_so_they_appear_in_the_list_from_the_server()
    {
        await _outbox.AddAsync(Draft("Sent on refresh"));
        await _vm.RefreshCommand.ExecuteAsync(null);
        Assert.Equal(["Sent on refresh"], _vm.Rows.Select(r => r.Title));
        Assert.False(_vm.Rows[0].IsDraft);
        Assert.Equal("Sent 1 saved request(s).", _vm.Status);
    }

    [Fact]
    public async Task A_refused_draft_shows_as_needs_attention()
    {
        var bad = Draft("Refused"); await _outbox.AddAsync(bad);
        await _outbox.MarkRejectedAsync(bad.Key, "Amount: out of range");
        await _vm.RefreshCommand.ExecuteAsync(null);
        Assert.Equal(("Needs attention: Amount: out of range", true), (_vm.Rows[0].Badge, _vm.Rows[0].NeedsAttention));
    }

    [Fact]
    public async Task Coming_back_online_sends_the_outbox_and_refreshes_by_itself()
    {
        _net.Switch(false); await _vm.RefreshCommand.ExecuteAsync(null);
        await _outbox.AddAsync(Draft("Queued offline"));
        Assert.False(_vm.IsOnline);

        _net.Switch(true);   // the OS raises ConnectivityChanged
        for (var i = 0; i < 200 && !(_vm.Rows.Count == 1 && !_vm.Rows[0].IsDraft); i++) await Task.Delay(20);

        Assert.True(_vm.IsOnline);
        Assert.Single(_api.Submitted);
        Assert.Equal(["Queued offline"], _vm.Rows.Select(r => r.Title));
    }

    [Fact]
    public async Task With_nothing_anywhere_the_list_is_empty_and_says_so()
    {
        await _vm.RefreshCommand.ExecuteAsync(null);
        Assert.True(_vm.IsEmpty);
    }
}
