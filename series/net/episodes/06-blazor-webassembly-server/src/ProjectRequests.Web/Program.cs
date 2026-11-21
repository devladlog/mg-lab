using ProjectRequests.Web.Client.Services;
using ProjectRequests.Web.Components;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddRazorComponents()
    .AddInteractiveServerComponents()           // Interactive Server: UI events over a SignalR circuit
    .AddInteractiveWebAssemblyComponents();     // Interactive WebAssembly: the .Client project, in the browser

// Server-side calls to the API (static SSR, Interactive Server, and PRERENDERING of WebAssembly pages).
// The WebAssembly page /requests/new injects IRequestsApi too: without this registration its prerender fails
// with "There is no registered service of type 'IRequestsApi'".
builder.Services.AddHttpClient<IRequestsApi, RequestsApiClient>(client =>
    client.BaseAddress = new Uri(builder.Configuration["RequestsApi:BaseUrl"]
        ?? throw new InvalidOperationException("RequestsApi:BaseUrl is missing.")));

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseWebAssemblyDebugging();
}
else
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
    app.UseHttpsRedirection();
}
app.UseStatusCodePagesWithReExecute("/not-found", createScopeForStatusCodePages: true);

app.UseAntiforgery();

app.MapStaticAssets();
app.MapRazorComponents<App>()
    .AddInteractiveServerRenderMode()
    .AddInteractiveWebAssemblyRenderMode()
    .AddAdditionalAssemblies(typeof(ProjectRequests.Web.Client._Imports).Assembly);

app.Run();
