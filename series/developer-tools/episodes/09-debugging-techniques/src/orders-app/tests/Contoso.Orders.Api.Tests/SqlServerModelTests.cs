using Contoso.Orders.Api;
using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Contoso.Orders.Api.Tests;

/// <summary>No SQL Server on the build machine, but EF Core can still generate the SQL Server schema
/// offline: this proves the model maps cleanly before Compose ever starts the database container.</summary>
public class SqlServerModelTests
{
    private static OrdersDb SqlServerContext() => new(new DbContextOptionsBuilder<OrdersDb>()
        .UseSqlServer("Server=db;Database=Orders;User Id=sa;Password=not-used;TrustServerCertificate=True")
        .Options);

    [Fact]
    public void Sql_server_create_script_has_the_expected_types()
    {
        using var db = SqlServerContext();
        var script = db.Database.GenerateCreateScript();
        Assert.Contains("CREATE TABLE [Orders]", script);
        Assert.Contains("[Id] int NOT NULL IDENTITY", script);
        Assert.Contains("[Customer] nvarchar(100) NOT NULL", script);
        Assert.Contains("[Total] decimal(10,2) NOT NULL", script);
        Assert.Contains("[Created] date NOT NULL", script);
        Assert.Contains("CREATE INDEX [IX_Orders_Created]", script);
    }

    [Theory]
    [InlineData("Sqlite", "Microsoft.EntityFrameworkCore.Sqlite")]
    [InlineData("SqlServer", "Microsoft.EntityFrameworkCore.SqlServer")]
    public void Provider_setting_selects_the_engine(string provider, string expected)
    {
        var services = new ServiceCollection().AddOrdersDb(Config(provider, "Data Source=x.db"));
        using var sp = services.BuildServiceProvider();
        using var scope = sp.CreateScope();
        Assert.Equal(expected, scope.ServiceProvider.GetRequiredService<OrdersDb>().Database.ProviderName);
    }

    [Fact]
    public void Unknown_provider_fails_fast_with_a_clear_message()
    {
        var ex = Assert.Throws<InvalidOperationException>(() =>
            new ServiceCollection().AddOrdersDb(Config("Postgres", "x")));
        Assert.Contains("use Sqlite or SqlServer", ex.Message);
    }

    [Fact]
    public void Missing_connection_string_fails_fast()
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(
            new Dictionary<string, string?> { ["Database:Provider"] = "SqlServer" }).Build();
        Assert.Throws<InvalidOperationException>(() => new ServiceCollection().AddOrdersDb(config));
    }

    [Fact]
    public void Double_underscore_environment_variables_map_to_configuration_sections()
    {
        // Compose sets ConnectionStrings__Orders; ASP.NET Core reads it as ConnectionStrings:Orders.
        Environment.SetEnvironmentVariable("CONTOSO_TEST_ConnectionStrings__Orders", "Server=db");
        var config = new ConfigurationBuilder().AddEnvironmentVariables("CONTOSO_TEST_").Build();
        Assert.Equal("Server=db", config.GetConnectionString("Orders"));
    }

    // Exactly what Compose produces from compose.yaml (folded YAML puts a space before "Password");
    // tests/test_compose.py checks this literal against the interpolated file.
    private const string ComposeConnectionString =
        "Server=db;Database=Orders;User Id=sa;TrustServerCertificate=True; Password=Demo-Passw0rd-only";

    [Fact]
    public void Compose_connection_string_parses_as_intended()
    {
        var cs = new SqlConnectionStringBuilder(ComposeConnectionString);
        Assert.Equal("db", cs.DataSource);
        Assert.Equal("Orders", cs.InitialCatalog);
        Assert.Equal("sa", cs.UserID);
        Assert.Equal("Demo-Passw0rd-only", cs.Password);
        Assert.True(cs.TrustServerCertificate);
        Assert.Equal(SqlConnectionEncryptOption.Mandatory, cs.Encrypt);   // still encrypted, just not validated
    }

    private static IConfiguration Config(string provider, string cs) => new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Database:Provider"] = provider,
            ["ConnectionStrings:Orders"] = cs,
        }).Build();
}
