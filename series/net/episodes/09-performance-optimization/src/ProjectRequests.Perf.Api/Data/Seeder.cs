using Microsoft.EntityFrameworkCore;

namespace ProjectRequests.Perf.Api.Data;

/// <summary>
/// Deterministic demo data: 3 departments, 400 requesters, N requests (seeded Random, so every run - and every
/// benchmark - sees the same rows). No migrations in this episode: EnsureCreated is enough for a throw-away file.
/// </summary>
public static class Seeder
{
    public const int RequesterCount = 400;

    public static async Task SeedAsync(PerfDbContext db, int requestCount, CancellationToken ct = default)
    {
        await db.Database.EnsureCreatedAsync(ct);
        if (await db.Departments.AnyAsync(ct) || requestCount <= 0) return;

        db.Departments.AddRange(
            new Department { Code = "FIN", Name = "Finance" },
            new Department { Code = "IT", Name = "Information Technology" },
            new Department { Code = "OPS", Name = "Operations" });
        for (var i = 1; i <= RequesterCount; i++)
            db.Requesters.Add(new Requester { Name = $"Requester {i:000}", Email = $"requester{i:000}@contoso.example" });
        await db.SaveChangesAsync(ct);

        var rng = new Random(42);
        var epoch = new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        for (var offset = 0; offset < requestCount; offset += 5000)
        {
            var batch = Math.Min(5000, requestCount - offset);
            for (var i = 0; i < batch; i++)
            {
                var budget = Math.Round((decimal)(rng.NextDouble() * 300_000 + 1_000), 2);
                db.Requests.Add(new ProjectRequest
                {
                    Title = $"Project {offset + i + 1:00000}",
                    Budget = budget,
                    Priority = budget >= 50_000 ? Priority.High : Priority.Standard,
                    Status = (RequestStatus)rng.Next(0, 3),
                    CreatedAtUtc = epoch.AddMinutes((offset + i) * 7),
                    DepartmentId = rng.Next(1, 4),
                    RequesterId = rng.Next(1, RequesterCount + 1),
                });
            }
            await db.SaveChangesAsync(ct);
            db.ChangeTracker.Clear();
        }
    }
}
