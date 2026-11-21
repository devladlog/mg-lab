using System.Net;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace ProjectRequests.Web.Tests;

/// <summary>
/// The real Blazor Web App host in memory, with the API replaced by the fake. What a browser gets on the first
/// request: prerendered HTML, before any circuit or WebAssembly runtime exists.
/// </summary>
public sealed class WebHostTests
{
    private sealed class WebFactory(Action<IServiceCollection> services) : WebApplicationFactory<Program>
    {
        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.UseEnvironment("Development");
            builder.ConfigureTestServices(services);
        }
    }

    private static WebFactory WithFakeApi(FakeRequestsApi api) =>
        new(s => s.Replace(ServiceDescriptor.Scoped<IRequestsApi>(_ => api)));

    [Fact]
    public async Task WebAssembly_page_is_prerendered_on_the_server_with_the_button_disabled()
    {
        await using var factory = WithFakeApi(new FakeRequestsApi());

        var html = await factory.CreateClient().GetStringAsync("/requests/new", Ct);

        Assert.Contains("Rendered by: <strong>Static</strong>", html);
        Assert.Contains("<button type=\"submit\" disabled>", html);
        Assert.Contains("\"type\":\"webassembly\"", html);                 // marker: the browser takes over with WebAssembly
    }

    [Fact]
    public async Task Interactive_Server_page_is_prerendered_and_its_state_is_persisted_in_the_page()
    {
        var api = new FakeRequestsApi();
        api.Requests.Add(FakeRequestsApi.Sample(1, 80_000m));
        await using var factory = WithFakeApi(api);

        var html = await factory.CreateClient().GetStringAsync("/requests/1", Ct);

        Assert.Contains("#1 · Laptop refresh", html);
        Assert.Contains("\"type\":\"server\"", html);                      // marker: the circuit takes over
        Assert.Contains("<!--Blazor-Server-Component-State:", html);       // [PersistentState] travels with the HTML
        Assert.Equal(1, api.GetCalls);
    }

    [Fact]
    public async Task Static_SSR_list_streams_the_loading_text_then_the_table()
    {
        var api = new FakeRequestsApi { ListDelay = TimeSpan.FromMilliseconds(300) };   // like a real HTTP call
        api.Requests.Add(FakeRequestsApi.Sample(1));
        await using var factory = WithFakeApi(api);

        var html = await factory.CreateClient().GetStringAsync("/requests", Ct);

        Assert.Contains("Loading requests…", html);                        // first chunk
        Assert.Contains("<blazor-ssr>", html);                             // streamed update, same response
        Assert.Contains("Laptop refresh", html);
    }

    /// <summary>
    /// The gotcha: register IRequestsApi only in the .Client project and the WebAssembly page can't even be
    /// prerendered, because prerendering runs on the SERVER, with the server's services.
    /// </summary>
    [Fact]
    public async Task Without_a_server_registration_the_WebAssembly_page_fails_to_prerender()
    {
        await using var factory = new WebFactory(s => s.RemoveAll<IRequestsApi>());

        var response = await factory.CreateClient().GetAsync("/requests/new", Ct);
        var body = await response.Content.ReadAsStringAsync(Ct);

        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Contains("There is no registered service of type 'ProjectRequests.Web.Client.Services.IRequestsApi'", body);
    }
}
