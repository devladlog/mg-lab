using Microsoft.AspNetCore.Components.WebAssembly.Hosting;
using ProjectRequests.Web.Client.Services;

var builder = WebAssemblyHostBuilder.CreateDefault(args);

// In the browser: wwwroot/appsettings.json is downloaded with the app (public - never put secrets there).
// The API lives on another origin, so it must allow this app's origin (CORS, see the API's Program.cs).
var apiBase = new Uri(builder.Configuration["RequestsApi:BaseUrl"]
    ?? throw new InvalidOperationException("RequestsApi:BaseUrl is missing in wwwroot/appsettings.json."));
builder.Services.AddScoped(_ => new HttpClient { BaseAddress = apiBase });
builder.Services.AddScoped<IRequestsApi, RequestsApiClient>();

await builder.Build().RunAsync();
