using Microsoft.EntityFrameworkCore;
using PurchaseRequests.Api.Data;

namespace PurchaseRequests.Tests;

/// <summary>
/// The app's managed identity gets only read/write on data, not DDL rights, so the schema is deployed by an
/// admin from sql/001-schema.sql. This test keeps that file identical to what EF Core expects for SQL Server.
/// No server needed: GenerateCreateScript works offline. Regenerate with UPDATE_SCHEMA=1 dotnet test.
/// </summary>
public class SchemaTests
{
    static string EpisodeRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !Directory.Exists(Path.Combine(dir.FullName, "sql"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("Episode root with sql/ not found.");
    }

    static string Generate()
    {
        var options = new DbContextOptionsBuilder<AppDbContext>()
            .UseSqlServer("Server=tcp:unused.invalid;Database=pr;Authentication=Active Directory Default").Options;
        using var db = new AppDbContext(options);
        return db.Database.GenerateCreateScript().ReplaceLineEndings("\n").Trim() + "\n";
    }

    [Fact]
    public void Committed_schema_matches_the_ef_model()
    {
        var path = Path.Combine(EpisodeRoot(), "sql", "001-schema.sql");
        var expected = Generate();
        if (Environment.GetEnvironmentVariable("UPDATE_SCHEMA") == "1") File.WriteAllText(path, expected);
        Assert.Equal(expected, File.ReadAllText(path).ReplaceLineEndings("\n"));
    }

    [Fact]
    public void Grant_script_gives_data_rights_only_and_protects_the_audit_table()
    {
        var sql = File.ReadAllText(Path.Combine(EpisodeRoot(), "sql", "002-grant-app.sql"));
        Assert.Contains("FROM EXTERNAL PROVIDER", sql);
        Assert.Contains("ALTER ROLE db_datareader ADD MEMBER", sql);
        Assert.Contains("ALTER ROLE db_datawriter ADD MEMBER", sql);
        Assert.Contains("DENY UPDATE, DELETE ON dbo.AuditEntries TO", sql);
        Assert.DoesNotContain("db_ddladmin ADD", sql);
        Assert.DoesNotContain("db_owner ADD", sql);
    }
}
