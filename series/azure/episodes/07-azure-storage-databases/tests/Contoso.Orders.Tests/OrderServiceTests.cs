using Contoso.Orders.Api.Orders;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Time.Testing;

namespace Contoso.Orders.Tests;

public class OrderServiceTests : IDisposable
{
    private readonly TestDb _db = new();
    private readonly FakeTimeProvider _time = new(new DateTimeOffset(2026, 11, 21, 10, 0, 0, TimeSpan.Zero));

    private OrderService NewService() => new(_db.NewContext(), _time);

    private static CreateOrderRequest Req(string customer = "alex-demo", params (string Sku, int Qty)[] lines) =>
        new(customer, (lines.Length == 0 ? [("MON-270", 2), ("DOC-100", 1)] : lines)
            .Select(l => new OrderLineRequest(l.Sku, l.Qty)).ToList());

    public void Dispose() => _db.Dispose();

    [Fact]
    public async Task Create_prices_the_order_with_the_discount()
    {
        var r = await NewService().CreateAsync("k1", Req(), default);
        Assert.Equal(CreateOutcome.Created, r.Outcome);
        // 2 x 219.99 + 129.00 = 568.98, minus 5 % (28.45) = 540.53
        Assert.Equal(540.53m, r.Order!.Total);
        Assert.Equal(2, r.Order.Lines.Count);
    }

    [Fact]
    public async Task Same_key_and_body_is_a_replay_of_the_same_order()
    {
        var first = await NewService().CreateAsync("k1", Req(), default);
        var again = await NewService().CreateAsync("k1", Req(), default);
        Assert.Equal(CreateOutcome.Replayed, again.Outcome);
        Assert.Equal(first.Order!.Id, again.Order!.Id);
        await using var ctx = _db.NewContext();
        Assert.Equal(1, await ctx.Orders.CountAsync());
    }

    [Fact]
    public async Task Line_order_doesnt_change_the_request_hash()
    {
        await NewService().CreateAsync("k1", Req("alex-demo", ("MON-270", 2), ("DOC-100", 1)), default);
        var again = await NewService().CreateAsync("k1", Req("alex-demo", ("DOC-100", 1), ("MON-270", 2)), default);
        Assert.Equal(CreateOutcome.Replayed, again.Outcome);
    }

    [Fact]
    public async Task Same_key_with_another_body_is_a_conflict()
    {
        await NewService().CreateAsync("k1", Req(), default);
        var other = await NewService().CreateAsync("k1", Req("alex-demo", ("CBL-001", 3)), default);
        Assert.Equal(CreateOutcome.KeyReused, other.Outcome);
    }

    [Fact]
    public async Task Unknown_sku_is_rejected_before_anything_is_written()
    {
        var r = await NewService().CreateAsync("k1", Req("alex-demo", ("XYZ-999", 1)), default);
        Assert.Equal(CreateOutcome.UnknownSku, r.Outcome);
        await using var ctx = _db.NewContext();
        Assert.False(await ctx.Orders.AnyAsync());
    }

    [Fact]
    public async Task The_database_rejects_a_second_row_with_the_same_key()
    {
        // What a retried INSERT (or a racing request) hits: the unique index, not our C# check
        await NewService().CreateAsync("k1", Req(), default);
        await using var ctx = _db.NewContext();
        ctx.Orders.Add(new Order { CustomerId = "x", IdempotencyKey = "k1", RequestHash = new string('0', 64) });
        var ex = await Assert.ThrowsAsync<DbUpdateException>(() => ctx.SaveChangesAsync());
        Assert.True(OrderService.IsUniqueViolation(ex));
    }

    [Fact]
    public async Task Other_constraint_errors_are_not_mistaken_for_a_duplicate_key()
    {
        await using var ctx = _db.NewContext();
        ctx.OrderLines.Add(new OrderLine { OrderId = 999, Sku = "CBL-001", Quantity = 1 }); // FK violation
        await ctx.Database.ExecuteSqlRawAsync("PRAGMA foreign_keys = ON;");
        var ex = await Assert.ThrowsAsync<DbUpdateException>(() => ctx.SaveChangesAsync());
        Assert.False(OrderService.IsUniqueViolation(ex));
    }

    [Fact]
    public async Task Keyset_paging_walks_every_order_once_even_with_equal_timestamps()
    {
        var svc = NewService();
        for (var i = 0; i < 5; i++)
        {
            await svc.CreateAsync($"k{i}", Req("alex-demo", ("CBL-001", i + 1)), default);
            if (i % 2 == 1) _time.Advance(TimeSpan.FromSeconds(1)); // pairs share a CreatedUtc
        }
        await svc.CreateAsync("other", Req("sam-demo", ("CBL-001", 1)), default);

        var seen = new List<long>();
        string? after = null;
        do
        {
            var page = await NewService().ListForCustomerAsync("alex-demo", after, 2, default);
            Assert.True(page.Items.Count <= 2);
            seen.AddRange(page.Items.Select(o => o.Id));
            after = page.Next;
        } while (after is not null);

        Assert.Equal([5, 4, 3, 2, 1], seen); // newest first, ties broken by id, sam's order excluded
    }

    [Fact]
    public async Task Page_size_is_capped()
    {
        var page = await NewService().ListForCustomerAsync("alex-demo", null, 10_000, default);
        Assert.Empty(page.Items);
        Assert.Null(page.Next);
        Assert.Equal(50, OrderService.MaxPageSize);
    }

    [Fact]
    public async Task A_tampered_cursor_is_a_format_error()
    {
        await Assert.ThrowsAsync<FormatException>(() => NewService().ListForCustomerAsync("alex-demo", "not-a-cursor!", 2, default));
    }

    [Fact]
    public void Cursor_round_trips()
    {
        var t = new DateTime(2026, 11, 21, 10, 0, 0, DateTimeKind.Utc).AddTicks(1234567);
        Assert.Equal((t, 42L), Cursor.Decode(Cursor.Encode(t, 42)));
    }

    [Fact]
    public async Task Cancel_needs_the_current_version()
    {
        var order = (await NewService().CreateAsync("k1", Req(), default)).Order!;

        Assert.Equal(CancelOutcome.VersionMismatch, (await NewService().CancelAsync(order.Id, Guid.Empty, default)).Outcome);
        var ok = await NewService().CancelAsync(order.Id, order.Version, default);
        Assert.Equal(CancelOutcome.Cancelled, ok.Outcome);
        Assert.NotEqual(order.Version, ok.Order!.Version);
        Assert.Equal(CancelOutcome.AlreadyCancelled, (await NewService().CancelAsync(order.Id, ok.Order.Version, default)).Outcome);
        Assert.Equal(CancelOutcome.NotFound, (await NewService().CancelAsync(9999, Guid.Empty, default)).Outcome);
    }

    [Fact]
    public async Task Concurrent_update_between_read_and_save_is_detected_by_the_database()
    {
        var order = (await NewService().CreateAsync("k1", Req(), default)).Order!;

        // Writer A reads the row...
        await using var a = _db.NewContext();
        var rowA = await a.Orders.SingleAsync(o => o.Id == order.Id);
        // ...writer B changes it in the meantime...
        await using (var b = _db.NewContext())
        {
            var rowB = await b.Orders.SingleAsync(o => o.Id == order.Id);
            rowB.Version = Guid.NewGuid();
            await b.SaveChangesAsync();
        }
        // ...so A's UPDATE ... WHERE Version = @old touches 0 rows
        rowA.Status = OrderStatus.Cancelled;
        rowA.Version = Guid.NewGuid();
        await Assert.ThrowsAsync<DbUpdateConcurrencyException>(() => a.SaveChangesAsync());
    }
}
