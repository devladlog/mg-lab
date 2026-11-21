using System.Collections.ObjectModel;
using Contoso.Mobile.Core.Api;
using Contoso.Mobile.Core.Models;
using Contoso.Mobile.Core.Offline;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Contoso.Mobile.Core.ViewModels;

/// <summary>One row of the list: either a request the server knows, or a draft still on this device.</summary>
public sealed record RequestRow(string Title, string Subtitle, string Badge, bool IsDraft, bool NeedsAttention);

/// <summary>Posts to the UI thread. MAUI: <c>MainThread.BeginInvokeOnMainThread</c>. Tests: runs inline.</summary>
public interface IUiThread { void Post(Action action); }

public partial class RequestListViewModel : ObservableObject
{
    private readonly IRequestsApi _api;
    private readonly IRequestCache _cache;
    private readonly IOutbox _outbox;
    private readonly SyncService _sync;
    private readonly IConnectivityService _network;
    private readonly IUiThread _ui;

    public RequestListViewModel(IRequestsApi api, IRequestCache cache, IOutbox outbox, SyncService sync,
        IConnectivityService network, IUiThread ui)
    {
        (_api, _cache, _outbox, _sync, _network, _ui) = (api, cache, outbox, sync, network, ui);
        _isOnline = network.IsOnline;
        network.Changed += OnNetworkChanged;
    }

    public ObservableCollection<RequestRow> Rows { get; } = [];

    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private bool _isOnline;
    [ObservableProperty] private string _status = "";
    [ObservableProperty] private bool _isEmpty;

    [RelayCommand]
    private async Task RefreshAsync()
    {
        IsBusy = true;
        try
        {
            if (_network.IsOnline)
            {
                var report = await _sync.FlushAsync();   // first send what the user already wrote...
                try
                {
                    var items = await _api.ListAsync();  // ...then read
                    await _cache.SaveAsync(items);
                    await ShowAsync(items, report.Sent > 0 ? $"Sent {report.Sent} saved request(s)." : "Up to date.");
                    return;
                }
                catch (ApiUnavailableException)
                {
                    // Connectivity says "online" but the server isn't reachable (Learn: Internet doesn't guarantee a connection).
                    await ShowAsync(await _cache.LoadAsync(), "Server not reachable. Showing the list saved on this device.");
                    return;
                }
            }
            await ShowAsync(await _cache.LoadAsync(), "Offline. Showing the list saved on this device.");
        }
        finally { IsBusy = false; }
    }

    private async Task ShowAsync(IReadOnlyList<RequestItem> items, string status)
    {
        var drafts = await _outbox.ListAsync();
        Rows.Clear();
        foreach (var d in drafts)   // drafts first: the user's own, not sent yet
            Rows.Add(new RequestRow(d.Title, $"{d.DepartmentCode} · {d.Amount:N0}",
                d.NeedsAttention ? $"Needs attention: {d.Error}" : "Waiting to be sent", IsDraft: true, d.NeedsAttention));
        foreach (var r in items.OrderByDescending(i => i.Id))
            Rows.Add(new RequestRow(r.Title, $"{r.Department} · {r.Amount:N0} · {r.RequestedBy}", BadgeFor(r.BudgetState), false, false));

        IsEmpty = Rows.Count == 0;
        Status = status;
    }

    private static string BadgeFor(string budgetState) => budgetState switch
    {
        "Reserved" => "Budget reserved",
        "Declined" => "Budget declined",
        "Pending" => "Budget check pending",
        _ => budgetState,
    };

    private void OnNetworkChanged(object? sender, EventArgs e) =>
        _ui.Post(() =>
        {
            IsOnline = _network.IsOnline;
            if (IsOnline) RefreshCommand.Execute(null);   // back online: send the outbox, refresh the list
        });
}
