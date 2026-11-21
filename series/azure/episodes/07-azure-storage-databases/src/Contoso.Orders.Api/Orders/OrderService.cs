using System.Text;
using Contoso.Orders.Api.Data;
using Microsoft.Data.SqlClient;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Api.Orders;

public enum CreateOutcome { Created, Replayed, KeyReused, UnknownSku }
public sealed record CreateResult(CreateOutcome Outcome, Order? Order, string? Error = null);

public enum CancelOutcome { Cancelled, NotFound, VersionMismatch, AlreadyCancelled }
public sealed record CancelResult(CancelOutcome Outcome, Order? Order);

public sealed class OrderService(OrdersDbContext db, TimeProvider time)
{
    public const int MaxPageSize = 50;

    /// <summary>
    /// Idempotent create. Same key + same body = the original order (replay); same key + another
    /// body = conflict. Two racing requests with one key both pass the lookup; the unique index
    /// lets exactly one INSERT win and the loser becomes a replay.
    /// </summary>
    public async Task<CreateResult> CreateAsync(string idempotencyKey, CreateOrderRequest request, CancellationToken ct)
    {
        var hash = OrderRules.RequestHash(request);
        var existing = await FindByKeyAsync(idempotencyKey, ct);
        if (existing is not null) return AsReplay(existing, hash);

        var unknown = request.Lines!.Select(l => l.Sku!).Where(s => !OrderRules.Catalogue.ContainsKey(s)).ToList();
        if (unknown.Count > 0) return new(CreateOutcome.UnknownSku, null, "unknown SKU: " + string.Join(", ", unknown));

        var lines = request.Lines!.Select(l => new OrderLine
        {
            Sku = l.Sku!, Quantity = l.Quantity, UnitPrice = OrderRules.Catalogue[l.Sku!],
        }).ToList();
        var subtotal = lines.Sum(l => OrderRules.Round(l.UnitPrice * l.Quantity));
        var discount = subtotal >= OrderRules.DiscountThreshold ? OrderRules.Round(subtotal * OrderRules.DiscountRate) : 0m;

        var order = new Order
        {
            CustomerId = request.CustomerId!,
            IdempotencyKey = idempotencyKey,
            RequestHash = hash,
            CreatedUtc = time.GetUtcNow().UtcDateTime,
            Total = subtotal - discount,
            Lines = lines,
        };
        db.Orders.Add(order);
        try
        {
            await db.SaveChangesAsync(ct);
            return new(CreateOutcome.Created, order);
        }
        catch (DbUpdateException ex) when (IsUniqueViolation(ex))
        {
            db.ChangeTracker.Clear();
            var winner = await FindByKeyAsync(idempotencyKey, ct)
                ?? throw new InvalidOperationException("Unique violation but no row with that key.", ex);
            return AsReplay(winner, hash);
        }
    }

    private static CreateResult AsReplay(Order existing, string hash) =>
        existing.RequestHash == hash ? new(CreateOutcome.Replayed, existing) : new(CreateOutcome.KeyReused, existing);

    private Task<Order?> FindByKeyAsync(string key, CancellationToken ct) =>
        db.Orders.AsNoTracking().Include(o => o.Lines).SingleOrDefaultAsync(o => o.IdempotencyKey == key, ct);

    public Task<Order?> GetAsync(long id, CancellationToken ct) =>
        db.Orders.AsNoTracking().Include(o => o.Lines).SingleOrDefaultAsync(o => o.Id == id, ct);

    /// <summary>
    /// Keyset (seek) paging: newest first, continue after the last row seen. Unlike OFFSET, the cost
    /// doesn't grow with the page number and rows inserted meanwhile don't shift the pages.
    /// </summary>
    public async Task<OrderPage> ListForCustomerAsync(string customerId, string? after, int take, CancellationToken ct)
    {
        take = Math.Clamp(take, 1, MaxPageSize);
        var q = db.Orders.AsNoTracking().Where(o => o.CustomerId == customerId);
        if (after is not null)
        {
            var (t, id) = Cursor.Decode(after);
            q = q.Where(o => o.CreatedUtc < t || (o.CreatedUtc == t && o.Id < id));
        }
        var rows = await q.OrderByDescending(o => o.CreatedUtc).ThenByDescending(o => o.Id)
            .Take(take + 1).Include(o => o.Lines).ToListAsync(ct);

        var page = rows.Take(take).ToList();
        var next = rows.Count > take ? Cursor.Encode(page[^1].CreatedUtc, page[^1].Id) : null;
        return new(page.Select(OrderDto.From).ToList(), next);
    }

    /// <summary>Optimistic concurrency: the caller must send the version (ETag) it last read.</summary>
    public async Task<CancelResult> CancelAsync(long id, Guid expectedVersion, CancellationToken ct)
    {
        var order = await db.Orders.Include(o => o.Lines).SingleOrDefaultAsync(o => o.Id == id, ct);
        if (order is null) return new(CancelOutcome.NotFound, null);
        if (order.Version != expectedVersion) return new(CancelOutcome.VersionMismatch, order);
        if (order.Status == OrderStatus.Cancelled) return new(CancelOutcome.AlreadyCancelled, order);

        order.Status = OrderStatus.Cancelled;
        order.Version = Guid.NewGuid();
        try
        {
            // UPDATE ... WHERE Id = @id AND Version = @expected: 0 rows if someone else got there first
            await db.SaveChangesAsync(ct);
            return new(CancelOutcome.Cancelled, order);
        }
        catch (DbUpdateConcurrencyException)
        {
            return new(CancelOutcome.VersionMismatch, order);
        }
    }

    internal static bool IsUniqueViolation(DbUpdateException ex) => ex.InnerException switch
    {
        SqlException sql => sql.Number is 2601 or 2627,                // duplicate key in unique index / constraint
        SqliteException lite => lite.SqliteExtendedErrorCode == 2067, // SQLITE_CONSTRAINT_UNIQUE
        _ => false,
    };
}

/// <summary>Opaque continuation token: base64url("ticks.id").</summary>
public static class Cursor
{
    public static string Encode(DateTime createdUtc, long id) =>
        Convert.ToBase64String(Encoding.ASCII.GetBytes($"{createdUtc.Ticks}.{id}")).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    public static (DateTime CreatedUtc, long Id) Decode(string cursor)
    {
        try
        {
            var b64 = cursor.Replace('-', '+').Replace('_', '/');
            b64 = b64.PadRight(b64.Length + (4 - b64.Length % 4) % 4, '=');
            var parts = Encoding.ASCII.GetString(Convert.FromBase64String(b64)).Split('.');
            return (new DateTime(long.Parse(parts[0]), DateTimeKind.Utc), long.Parse(parts[1]));
        }
        catch (Exception ex) when (ex is FormatException or IndexOutOfRangeException or ArgumentOutOfRangeException or OverflowException)
        {
            throw new FormatException("Invalid cursor.", ex);
        }
    }
}
