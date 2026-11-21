using System.Net;
using System.Net.Http.Json;
using Contoso.Orders.Api.Data;
using Contoso.Orders.Api.Invoices;
using Contoso.Orders.Api.Orders;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace Contoso.Orders.Tests;

/// <summary>The real HTTP pipeline on SQLite in memory, with a recording invoice store.</summary>
public sealed class ApiFactory : WebApplicationFactory<Program>
{
    private readonly SqliteConnection _connection = new("Data Source=:memory:");
    public RecordingInvoiceStore Invoices { get; } = new();
    public bool InvoicesDisabled { get; init; }

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        _connection.Open();
        builder.ConfigureServices(s =>
        {
            s.RemoveAll<DbContextOptions<OrdersDbContext>>();
            s.RemoveAll<OrdersDbContext>();
            s.AddDbContext<OrdersDbContext>(o => o.UseSqlite(_connection));
            s.RemoveAll<IInvoiceStore>();
            if (InvoicesDisabled) s.AddSingleton<IInvoiceStore, DisabledInvoiceStore>();
            else s.AddSingleton<IInvoiceStore>(Invoices);
        });
    }

    protected override void ConfigureClient(HttpClient client)
    {
        using var scope = Services.CreateScope();
        scope.ServiceProvider.GetRequiredService<OrdersDbContext>().Database.EnsureCreated();
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        _connection.Dispose();
    }
}

public sealed class RecordingInvoiceStore : IInvoiceStore
{
    public List<long> Saved { get; } = [];
    public Task SaveAsync(Order order, CancellationToken ct) { lock (Saved) Saved.Add(order.Id); return Task.CompletedTask; }
    public Task<InvoiceLink> GetReadLinkAsync(Order order, TimeSpan lifetime, CancellationToken ct) =>
        Task.FromResult(new InvoiceLink(new Uri($"https://example.invalid/invoices/{order.Id}.json?sig=x"), DateTimeOffset.UnixEpoch.Add(lifetime)));
}

public class ApiTests : IDisposable
{
    private readonly ApiFactory _factory = new();
    private readonly HttpClient _http;
    private static readonly object Order = new { customerId = "alex-demo", lines = new[] { new { sku = "MON-270", quantity = 2 }, new { sku = "DOC-100", quantity = 1 } } };

    public ApiTests() => _http = _factory.CreateClient();
    public void Dispose() => _factory.Dispose();

    private Task<HttpResponseMessage> Post(object body, string? key)
    {
        var msg = new HttpRequestMessage(HttpMethod.Post, "/orders") { Content = JsonContent.Create(body) };
        if (key is not null) msg.Headers.Add("Idempotency-Key", key);
        return _http.SendAsync(msg);
    }

    [Fact]
    public async Task Missing_idempotency_key_is_400()
    {
        Assert.Equal(HttpStatusCode.BadRequest, (await Post(Order, null)).StatusCode);
    }

    [Fact]
    public async Task Create_then_replay_then_conflict()
    {
        var created = await Post(Order, "k1");
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        Assert.NotNull(created.Headers.ETag);
        var dto = (await created.Content.ReadFromJsonAsync<OrderDto>())!;
        Assert.Equal($"/orders/{dto.Id}", created.Headers.Location!.OriginalString);

        var replay = await Post(Order, "k1");
        Assert.Equal(HttpStatusCode.OK, replay.StatusCode);
        Assert.Equal("true", replay.Headers.GetValues("Idempotent-Replay").Single());
        Assert.Equal(dto.Id, (await replay.Content.ReadFromJsonAsync<OrderDto>())!.Id);

        var other = new { customerId = "alex-demo", lines = new[] { new { sku = "CBL-001", quantity = 1 } } };
        Assert.Equal(HttpStatusCode.Conflict, (await Post(other, "k1")).StatusCode);

        // the invoice is (re)written on create and on replay: same blob name, so it's an overwrite
        Assert.Equal([dto.Id, dto.Id], _factory.Invoices.Saved);
    }

    [Fact]
    public async Task Bad_shape_is_400_and_unknown_sku_is_422()
    {
        var bad = new { customerId = "alex-demo", lines = new[] { new { sku = "nope", quantity = 1 } } };
        Assert.Equal(HttpStatusCode.BadRequest, (await Post(bad, "k1")).StatusCode);
        var unknown = new { customerId = "alex-demo", lines = new[] { new { sku = "XYZ-999", quantity = 1 } } };
        Assert.Equal(HttpStatusCode.UnprocessableEntity, (await Post(unknown, "k2")).StatusCode);
        Assert.Empty(_factory.Invoices.Saved);
    }

    [Fact]
    public async Task Cancel_requires_if_match_and_rejects_a_stale_etag()
    {
        var created = await Post(Order, "k1");
        var id = (await created.Content.ReadFromJsonAsync<OrderDto>())!.Id;
        var etag = created.Headers.ETag!.Tag;

        Assert.Equal((HttpStatusCode)428, (await _http.PostAsync($"/orders/{id}/cancel", null)).StatusCode);

        var stale = new HttpRequestMessage(HttpMethod.Post, $"/orders/{id}/cancel");
        stale.Headers.TryAddWithoutValidation("If-Match", "\"00000000000000000000000000000000\"");
        Assert.Equal(HttpStatusCode.PreconditionFailed, (await _http.SendAsync(stale)).StatusCode);

        var ok = new HttpRequestMessage(HttpMethod.Post, $"/orders/{id}/cancel");
        ok.Headers.TryAddWithoutValidation("If-Match", etag);
        var res = await _http.SendAsync(ok);
        Assert.Equal(HttpStatusCode.OK, res.StatusCode);
        Assert.NotEqual(etag, res.Headers.ETag!.Tag);
        Assert.Equal("Cancelled", (await res.Content.ReadFromJsonAsync<OrderDto>())!.Status);
    }

    [Fact]
    public async Task Paging_endpoint_returns_a_cursor_and_rejects_a_bad_one()
    {
        for (var i = 0; i < 3; i++) await Post(new { customerId = "sam-demo", lines = new[] { new { sku = "CBL-001", quantity = i + 1 } } }, $"p{i}");
        var page = (await _http.GetFromJsonAsync<OrderPage>("/customers/sam-demo/orders?take=2"))!;
        Assert.Equal(2, page.Items.Count);
        Assert.NotNull(page.Next);
        var rest = (await _http.GetFromJsonAsync<OrderPage>($"/customers/sam-demo/orders?take=2&after={page.Next}"))!;
        Assert.Single(rest.Items);
        Assert.Null(rest.Next);
        Assert.Equal(HttpStatusCode.BadRequest, (await _http.GetAsync("/customers/sam-demo/orders?after=%%%")).StatusCode);
    }

    [Fact]
    public async Task Invoice_link_and_health()
    {
        var id = (await (await Post(Order, "k1")).Content.ReadFromJsonAsync<OrderDto>())!.Id;
        var link = await _http.GetFromJsonAsync<Dictionary<string, object>>($"/orders/{id}/invoice");
        Assert.Contains($"/invoices/{id}.json", link!["url"].ToString());
        Assert.Equal(HttpStatusCode.NotFound, (await _http.GetAsync("/orders/9999/invoice")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await _http.GetAsync("/healthz")).StatusCode);
    }

    [Fact]
    public async Task Invoice_endpoint_is_503_when_storage_isnt_configured()
    {
        using var f = new ApiFactory { InvoicesDisabled = true };
        var http = f.CreateClient();
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await http.GetAsync("/orders/1/invoice")).StatusCode);
    }
}
