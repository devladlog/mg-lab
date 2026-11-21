using Contoso.Mobile.Core.Api;
using Contoso.Mobile.Core.Offline;
using Contoso.Mobile.Core.ViewModels;
using Contoso.Mobile.Services;
using Contoso.Mobile.Views;
using Microsoft.Extensions.Logging;

namespace Contoso.Mobile;

public static class MauiProgram
{
	public static MauiApp CreateMauiApp()
	{
		var builder = MauiApp.CreateBuilder();
		builder.UseMauiApp<App>();

		// The platform bits (network state, UI thread) are tiny adapters; everything else is plain C# from Contoso.Mobile.Core.
		builder.Services.AddSingleton<IConnectivityService, MauiConnectivityService>();
		builder.Services.AddSingleton<IUiThread, MauiUiThread>();
		builder.Services.AddSingleton(TimeProvider.System);

		var data = FileSystem.AppDataDirectory;   // private to the app, survives restarts
		builder.Services.AddSingleton<IOutbox>(_ => new FileOutbox(Path.Combine(data, "outbox.json")));
		builder.Services.AddSingleton<IRequestCache>(_ => new FileRequestCache(Path.Combine(data, "requests-cache.json")));

		// One HttpClient for the app (the gateway from episode 11). Android emulator: 10.0.2.2, otherwise localhost;
		// a physical device sets the Preferences key "ApiBaseUrl" to the dev machine's address.
		builder.Services.AddSingleton<IRequestsApi>(_ => new RequestsApi(new HttpClient
		{
			BaseAddress = ApiEndpoints.BaseAddress(
				DeviceInfo.Platform == DevicePlatform.Android ? "Android" : "Other",
				Preferences.Get("ApiBaseUrl", string.Empty)),
			Timeout = TimeSpan.FromSeconds(10),
		}));

		builder.Services.AddSingleton<SyncService>();
		builder.Services.AddSingleton<RequestListViewModel>();   // one list for the life of the app
		builder.Services.AddTransient<NewRequestViewModel>();
		builder.Services.AddTransient<RequestListPage>();
		builder.Services.AddTransient<NewRequestPage>();

#if DEBUG
		builder.Logging.AddDebug();
#endif
		return builder.Build();
	}
}
