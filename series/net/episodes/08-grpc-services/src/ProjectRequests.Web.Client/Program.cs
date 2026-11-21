using Microsoft.AspNetCore.Components.WebAssembly.Hosting;
using Microsoft.Extensions.Logging;
using ProjectRequests.Feed;
using ProjectRequests.Web.Client.Services;

var builder = WebAssemblyHostBuilder.CreateDefault(args);

// In the browser: wwwroot/appsettings.json is downloaded with the app (public - never put secrets there).
// The API lives on another origin, so it must allow this app's origin (CORS, see the API's Program.cs).
var apiBase = new Uri(builder.Configuration["RequestsApi:BaseUrl"]
    ?? throw new InvalidOperationException("RequestsApi:BaseUrl is missing in wwwroot/appsettings.json."));
builder.Services.AddScoped(_ => new HttpClient { BaseAddress = apiBase });
builder.Services.AddScoped<IRequestsApi, RequestsApiClient>();

// Episode 7: the live board's SignalR connection, from the browser to the API's hub (another origin: the API's
// "signalr" CORS policy must allow this app). The page creates one when it becomes interactive and disposes it.
builder.Services.AddSingleton<IRequestsFeedFactory>(sp => new RequestsFeedFactory(apiBase, sp.GetService<ILoggerFactory>()));

await builder.Build().RunAsync();
