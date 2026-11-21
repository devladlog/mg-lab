using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using ProjectRequests.Perf.Api.Data;

namespace ProjectRequests.Perf.Api;

public static class PerfSetup
{
    /// <summary>SQLite context. Any IInterceptor registered in DI is added, which is how the tests count SQL commands.</summary>
    public static IServiceCollection AddPerfData(this IServiceCollection services, IConfiguration config)
    {
        var connectionString = config.GetConnectionString("Requests") ?? "Data Source=perf.db";
        services.AddDbContext<PerfDbContext>((sp, o) => o
            .UseSqlite(connectionString)
            .AddInterceptors(sp.GetServices<IInterceptor>().ToArray()));
        return services;
    }
}
