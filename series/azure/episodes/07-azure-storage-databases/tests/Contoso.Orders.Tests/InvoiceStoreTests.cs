using System.Net;
using System.Text.Json;
using System.Web;
using Contoso.Orders.Api.Invoices;
using Contoso.Orders.Api.Orders;
using Microsoft.Extensions.Time.Testing;

namespace Contoso.Orders.Tests;

[Collection("azurite")]
public class InvoiceStoreTests(AzuriteFixture azurite) : IAsyncLifetime
{
    private readonly string _container = "invoices-" + Guid.NewGuid().ToString("N")[..8];
    private readonly FakeTimeProvider _time = new(DateTimeOffset.UtcNow);

    public async Task InitializeAsync() => await azurite.NewServiceClient().CreateBlobContainerAsync(_container);
    public Task DisposeAsync() => Task.CompletedTask;

    private BlobInvoiceStore NewStore() => new(azurite.NewServiceClient(), _container, _time);

    private static Order NewOrder(long id) => new()
    {
        Id = id, CustomerId = "alex-demo", IdempotencyKey = "k", RequestHash = "h", Total = 540.53m,
        CreatedUtc = new DateTime(2026, 11, 21, 10, 0, 0, DateTimeKind.Utc),
        Lines = [new OrderLine { Sku = "MON-270", Quantity = 2, UnitPrice = 219.99m }],
    };

    [Fact]
    public void Blob_name_is_date_prefixed_and_named_after_the_order() =>
        Assert.Equal("2026/11/1001.json", BlobInvoiceStore.BlobName(NewOrder(1001)));

    [Fact]
    public async Task Saved_invoice_downloads_through_a_read_only_user_delegation_sas()
    {
        var store = NewStore();
        await store.SaveAsync(NewOrder(1001), default);
        var link = await store.GetReadLinkAsync(NewOrder(1001), TimeSpan.FromMinutes(10), default);

        var q = HttpUtility.ParseQueryString(link.Url.Query);
        Assert.Equal("r", q["sp"]);          // read only
        Assert.Equal("b", q["sr"]);          // this blob, not the container
        Assert.Equal("https", q["spr"]);     // HTTPS only
        Assert.NotNull(q["skoid"]);          // user delegation: signed with a key issued to an Entra identity
        Assert.NotNull(q["sig"]);

        using var http = AzuriteFixture.InsecureHttp();
        var res = await http.GetAsync(link.Url);
        Assert.Equal(HttpStatusCode.OK, res.StatusCode);
        Assert.Equal("application/json", res.Content.Headers.ContentType!.MediaType);
        var doc = JsonDocument.Parse(await res.Content.ReadAsStringAsync()).RootElement;
        Assert.Equal(1001, doc.GetProperty("id").GetInt64());
        Assert.Equal(540.53m, doc.GetProperty("total").GetDecimal());
    }

    [Fact]
    public async Task Changing_the_sas_permissions_breaks_the_signature()
    {
        var store = NewStore();
        await store.SaveAsync(NewOrder(1002), default);
        var link = await store.GetReadLinkAsync(NewOrder(1002), TimeSpan.FromMinutes(10), default);
        var tampered = new Uri(link.Url.ToString().Replace("sp=r&", "sp=rw&"));
        Assert.NotEqual(link.Url, tampered);

        using var http = AzuriteFixture.InsecureHttp();
        Assert.Equal(HttpStatusCode.Forbidden, (await http.GetAsync(tampered)).StatusCode);
    }

    [Fact]
    public async Task The_link_cannot_write()
    {
        var store = NewStore();
        await store.SaveAsync(NewOrder(1003), default);
        var link = await store.GetReadLinkAsync(NewOrder(1003), TimeSpan.FromMinutes(10), default);

        using var http = AzuriteFixture.InsecureHttp();
        var put = new HttpRequestMessage(HttpMethod.Put, link.Url) { Content = new StringContent("{}") };
        put.Headers.Add("x-ms-blob-type", "BlockBlob");
        Assert.Equal(HttpStatusCode.Forbidden, (await http.SendAsync(put)).StatusCode);
    }

    [Fact]
    public async Task Saving_twice_overwrites_the_same_blob()
    {
        var store = NewStore();
        await store.SaveAsync(NewOrder(1004), default);
        await store.SaveAsync(NewOrder(1004), default);
        var blobs = new List<string>();
        await foreach (var b in azurite.NewServiceClient().GetBlobContainerClient(_container).GetBlobsAsync()) blobs.Add(b.Name);
        Assert.Equal(["2026/11/1004.json"], blobs);
    }

    [Fact]
    public async Task Link_lifetime_is_capped_at_one_hour()
    {
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() =>
            NewStore().GetReadLinkAsync(NewOrder(1), TimeSpan.FromHours(2), default));
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() =>
            NewStore().GetReadLinkAsync(NewOrder(1), TimeSpan.Zero, default));
    }

    [Fact]
    public async Task One_delegation_key_serves_many_links_until_it_would_expire()
    {
        var store = NewStore();
        var a = HttpUtility.ParseQueryString((await store.GetReadLinkAsync(NewOrder(1), TimeSpan.FromMinutes(10), default)).Url.Query);
        var b = HttpUtility.ParseQueryString((await store.GetReadLinkAsync(NewOrder(2), TimeSpan.FromMinutes(10), default)).Url.Query);
        Assert.Equal(a["ske"], b["ske"]); // same key (same key expiry)

        _time.Advance(TimeSpan.FromMinutes(115)); // the 2-hour key can't cover a 10-minute link any more
        var c = HttpUtility.ParseQueryString((await store.GetReadLinkAsync(NewOrder(3), TimeSpan.FromMinutes(10), default)).Url.Query);
        Assert.NotEqual(a["ske"], c["ske"]);
    }
}
