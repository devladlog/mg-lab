using Contoso.Mobile.Core.Offline;
using Contoso.Mobile.Core.ViewModels;
using Microsoft.Maui.Networking;

namespace Contoso.Mobile.Services;

/// <summary>
/// <c>Connectivity.Current</c> as the app's <see cref="IConnectivityService"/>. Learn: <c>NetworkAccess.Internet</c> only says a
/// connection exists, not that the server is reachable. So the app never trusts it alone: a failed call is "unavailable" too.
/// </summary>
public sealed class MauiConnectivityService : IConnectivityService, IDisposable
{
	public MauiConnectivityService() => Connectivity.Current.ConnectivityChanged += OnChanged;

	public bool IsOnline => Connectivity.Current.NetworkAccess == NetworkAccess.Internet;

	public event EventHandler? Changed;

	private void OnChanged(object? sender, ConnectivityChangedEventArgs e) => Changed?.Invoke(this, EventArgs.Empty);

	public void Dispose() => Connectivity.Current.ConnectivityChanged -= OnChanged;
}

public sealed class MauiUiThread : IUiThread
{
	public void Post(Action action) => MainThread.BeginInvokeOnMainThread(action);
}
