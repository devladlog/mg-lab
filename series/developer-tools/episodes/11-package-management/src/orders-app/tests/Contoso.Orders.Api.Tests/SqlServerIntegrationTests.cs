using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Data.SqlClient;
using Microsoft.Extensions.DependencyInjection;

namespace Contoso.Orders.Api.Tests;

/// <summary>Runs only when ORDERS_SQLSERVER_TESTS holds a connection string (scripts/e2e.sh sets it after
/// "docker compose up --wait" in CI and on the recording laptop). Everywhere else these tests are skipped,
/// not passed: the test report shows them as skipped.</summary>
public sealed class SqlServerFactAttribute : FactAttribute
{
    public const string Variable = "ORDERS_SQLSERVER_TESTS";

    public SqlServerFactAttribute()
    {
        if (string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(Variable)))
            Skip = $"{Variable} is not set (no SQL Server here)";
    }
}

/// <summary>The real app on a real SQL Server, in its own throwaway database.</summary>
public sealed class SqlServerApiFactory : WebApplicationFactory<Program>
{
    public string ConnectionString { get; } = WithUniqueDatabase(
        Environment.GetEnvironmentVariable(SqlServerFactAttribute.Variable) ?? "");

    private static string WithUniqueDatabase(string cs) => cs.Length == 0 ? cs
        : new SqlConnectionStringBuilder(cs) { InitialCatalog = $"OrdersIt_{Guid.NewGuid():N}" }.ConnectionString;

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseSetting("Database:Provider", "SqlServer");
        builder.UseSetting("ConnectionStrings:Orders", ConnectionString);
        builder.UseSetting("Orders:SeedCount", "120");
    }

    public override async ValueTask DisposeAsync()
    {
        if (ConnectionString.Length > 0)
        {
            using var scope = Services.CreateScope();
            await scope.ServiceProvider.GetRequiredService<OrdersDb>().Database.EnsureDeletedAsync();
        }
        await base.DisposeAsync();
    }
}

[Trait("Category", "SqlServer")]
public class SqlServerIntegrationTests(SqlServerApiFactory factory) : IClassFixture<SqlServerApiFactory>
{
    [SqlServerFact]
    public async Task Healthz_reports_sql_server()
    {
        var body = await factory.CreateClient().GetFromJsonAsync<JsonElement>("/healthz");
        Assert.Equal("ok", body.GetProperty("status").GetString());
        Assert.Equal("SqlServer", body.GetProperty("database").GetString());
    }

    [SqlServerFact]
    public async Task Schema_is_created_and_seeded()
    {
        var page = await factory.CreateClient().GetFromJsonAsync<Page<Order>>("/orders?page=2&pageSize=50");
        Assert.True(page!.Total >= 120);
        Assert.Equal(51, page.Items[0].Id);
    }

    [SqlServerFact]
    public async Task Decimal_and_date_round_trip_through_sql_server()
    {
        var client = factory.CreateClient();
        var response = await client.PostAsJsonAsync("/orders", new NewOrder("Alex Demo", 1234.56m));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);

        var read = await client.GetFromJsonAsync<Order>(response.Headers.Location);
        Assert.Equal(1234.56m, read!.Total);                                  // decimal(10,2)
        Assert.Equal(DateOnly.FromDateTime(DateTime.UtcNow), read.Created);  // date
    }

    [SqlServerFact]
    public async Task Customer_longer_than_the_column_is_rejected_before_sql_server()
    {
        var response = await factory.CreateClient().PostAsJsonAsync("/orders", new NewOrder(new string('x', 101), 10m));
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);       // not a 500 from a truncation error
    }
}
