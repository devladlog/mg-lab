using System.Diagnostics.Metrics;
using System.Data.Common;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using ProjectRequests.Perf.Api.Telemetry;

namespace ProjectRequests.Perf.Tests;

/// <summary>Counts every SQL command EF Core sends. Registered as an IInterceptor, which the API adds to its DbContext.</summary>
public sealed class CommandCounter : DbCommandInterceptor
{
    private int _count;
    public int Count => Volatile.Read(ref _count);
    public void Reset() => Interlocked.Exchange(ref _count, 0);

    /// <summary>Optional delay per command, to widen the window in which concurrent callers overlap.</summary>
    public TimeSpan Delay { get; set; }

    public override InterceptionResult<DbDataReader> ReaderExecuting(DbCommand c, CommandEventData e, InterceptionResult<DbDataReader> r)
    {
        Interlocked.Increment(ref _count);
        if (Delay > TimeSpan.Zero) Thread.Sleep(Delay);
        return r;
    }

    public override async ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(
        DbCommand c, CommandEventData e, InterceptionResult<DbDataReader> r, CancellationToken ct = default)
    {
        Interlocked.Increment(ref _count);
        if (Delay > TimeSpan.Zero) await Task.Delay(Delay, ct);
        return r;
    }
}

/// <summary>The API on an in-memory test server with its own SQLite file (300 requests) and SQL command counter.</summary>
public sealed class PerfFactory : WebApplicationFactory<Program>
{
    private readonly string _dbPath = Path.Combine(Path.GetTempPath(), $"perf-test-{Guid.NewGuid():N}.db");
    private readonly bool _enableSlow;

    public CommandCounter Commands { get; } = new();

    public PerfFactory(bool enableSlow = false) => _enableSlow = enableSlow;

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Production");
        builder.UseSetting("ConnectionStrings:Requests", $"Data Source={_dbPath}");
        builder.UseSetting("Perf:SeedCount", "300");
        builder.UseSetting("Perf:EnableSlowEndpoint", _enableSlow ? "true" : "false");
        builder.ConfigureServices(s => s.AddSingleton<IInterceptor>(Commands));
    }

    /// <summary>Records one counter of this app instance only: meters made by IMeterFactory are scoped to it.</summary>
    public MeterRecorder Record(string instrumentName) => new(Services.GetRequiredService<IMeterFactory>(), instrumentName);

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        if (!disposing) return;
        Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
        try { File.Delete(_dbPath); } catch (IOException) { /* temp file, best effort */ }
    }
}

public sealed class MeterRecorder : IDisposable
{
    private readonly MeterListener _listener = new();
    private long _total;
    public long Total => Interlocked.Read(ref _total);

    public MeterRecorder(IMeterFactory factory, string instrumentName)
    {
        _listener.InstrumentPublished = (instrument, listener) =>
        {
            if (instrument.Meter.Name == RequestMetrics.MeterName
                && ReferenceEquals(instrument.Meter.Scope, factory)
                && instrument.Name == instrumentName)
                listener.EnableMeasurementEvents(instrument);
        };
        _listener.SetMeasurementEventCallback<long>((_, value, _, _) => Interlocked.Add(ref _total, value));
        _listener.Start();
    }

    public void Dispose() => _listener.Dispose();
}
