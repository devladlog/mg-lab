using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.SqlServer.TransactSql.ScriptDom;
using TenantApi.Data;
using TenantApi.Tenancy;

namespace TenantApi.Tests;

/// <summary>
/// The T-SQL cannot run in this container (no SQL Server). It is parsed with Microsoft's own T-SQL parser
/// (ScriptDom, SQL Server 2022 grammar) and cross-checked against the EF Core model, so the two cannot drift.
/// Behaviour in a real database is proven in the lab (demo.md).
/// </summary>
public class SqlScriptTests
{
    static IList<TSqlBatch> Parse(string file, string? appIdentity = "app-saas-test")
    {
        var text = File.ReadAllText(Paths.Of("sql", file)).Replace("$(AppIdentity)", appIdentity);
        var parser = new TSql160Parser(initialQuotedIdentifiers: true);
        var fragment = parser.Parse(new StringReader(text), out var errors);
        Assert.True(errors.Count == 0, $"{file}: {string.Join("; ", errors.Select(e => $"line {e.Line}: {e.Message}"))}");
        return ((TSqlScript)fragment).Batches;
    }

    static List<T> Find<T>(IEnumerable<TSqlBatch> batches) where T : TSqlFragment
    {
        var v = new Collector<T>();
        foreach (var b in batches) b.Accept(v);
        return v.Found;
    }

    sealed class Collector<T> : TSqlFragmentVisitor where T : TSqlFragment
    {
        public List<T> Found { get; } = [];
        public override void Visit(TSqlFragment fragment) { if (fragment is T t) Found.Add(t); }
    }

    static string Table(SchemaObjectName n) => $"{n.SchemaIdentifier?.Value ?? "dbo"}.{n.BaseIdentifier.Value}";
    static string Table(SecurityTargetObjectName n) { var ids = n.MultiPartIdentifier.Identifiers; return ids.Count == 1 ? $"dbo.{ids[0].Value}" : $"{ids[^2].Value}.{ids[^1].Value}"; }

    static (Dictionary<string, HashSet<string>> sqlColumns, Dictionary<string, HashSet<string>> efColumns, HashSet<string> efTenantScoped) Model()
    {
        var sql = new Dictionary<string, HashSet<string>>(StringComparer.OrdinalIgnoreCase);
        foreach (var ct in Find<CreateTableStatement>(Parse("001-schema.sql")))
            sql[Table(ct.SchemaObjectName)] = ct.Definition.ColumnDefinitions.Select(c => c.ColumnIdentifier.Value).ToHashSet(StringComparer.OrdinalIgnoreCase);

        using var conn = new SqliteConnection("DataSource=:memory:");
        using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseSqlite(conn).Options, new TenantContext());
        var ef = new Dictionary<string, HashSet<string>>(StringComparer.OrdinalIgnoreCase);
        var scoped = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var et in db.Model.GetEntityTypes())
        {
            var table = $"dbo.{et.GetTableName()}";
            ef[table] = et.GetProperties().Select(p => p.GetColumnName()).ToHashSet(StringComparer.OrdinalIgnoreCase);
            if (typeof(ITenantScoped).IsAssignableFrom(et.ClrType)) scoped.Add(table);
        }
        return (sql, ef, scoped);
    }

    [Theory]
    [InlineData("001-schema.sql")]
    [InlineData("002-rls.sql")]
    [InlineData("003-grant-app.sql")]
    [InlineData("verify-rls.sql")]
    public void Every_script_parses_as_T_SQL(string file) => Assert.NotEmpty(Parse(file));

    [Fact]
    public void The_schema_script_and_the_EF_model_have_the_same_tables_and_columns()
    {
        var (sql, ef, _) = Model();
        Assert.Equal(ef.Keys.OrderBy(k => k), sql.Keys.OrderBy(k => k));
        foreach (var table in ef.Keys)
            Assert.True(ef[table].SetEquals(sql[table]), $"{table}: EF has [{string.Join(",", ef[table])}], SQL has [{string.Join(",", sql[table])}]");
    }

    [Fact]
    public void Every_tenant_scoped_table_has_a_filter_and_both_block_predicates_in_the_policy()
    {
        var (_, _, scoped) = Model();
        Assert.NotEmpty(scoped);
        var policy = Assert.Single(Find<CreateSecurityPolicyStatement>(Parse("002-rls.sql")));
        Assert.Contains(policy.SecurityPolicyOptions, o => o.OptionKind == SecurityPolicyOptionKind.State && o.OptionState == OptionState.On);

        foreach (var table in scoped)
        {
            var preds = policy.SecurityPredicateActions.Where(a => Table(a.TargetObjectName) == table).ToList();
            Assert.Contains(preds, p => p.SecurityPredicateType == SecurityPredicateType.Filter);
            Assert.Contains(preds, p => p.SecurityPredicateType == SecurityPredicateType.Block && p.SecurityPredicateOperation == SecurityPredicateOperation.AfterInsert);
            Assert.Contains(preds, p => p.SecurityPredicateType == SecurityPredicateType.Block && p.SecurityPredicateOperation == SecurityPredicateOperation.AfterUpdate);
        }
        // and nothing else is under the policy by accident
        Assert.True(policy.SecurityPredicateActions.Select(a => Table(a.TargetObjectName)).ToHashSet().SetEquals(scoped));
    }

    [Fact]
    public void The_predicate_function_is_schema_bound_and_compares_the_row_to_SESSION_CONTEXT()
    {
        var text = File.ReadAllText(Paths.Of("sql", "002-rls.sql"));
        Assert.Matches(new Regex(@"WITH\s+SCHEMABINDING", RegexOptions.IgnoreCase), text);
        Assert.Matches(new Regex(@"SESSION_CONTEXT\(N'TenantId'\)", RegexOptions.IgnoreCase), text);
        Assert.Matches(new Regex(@"SCHEMABINDING\s*=\s*ON", RegexOptions.IgnoreCase), text);
        // The predicate must not fall back to "allow" when the session has no tenant.
        Assert.DoesNotMatch(new Regex(@"IS\s+NULL", RegexOptions.IgnoreCase), text.Split("CREATE FUNCTION")[1]);
    }

    [Fact]
    public void The_interceptor_runs_sp_set_session_context_read_only_for_the_key_the_policy_reads()
    {
        var exec = Assert.Single(Find<ExecuteStatement>(Parse_Text(TenantSessionContextInterceptor.SetSessionContextSql)));
        var proc = ((ExecutableProcedureReference)exec.ExecuteSpecification.ExecutableEntity).ProcedureReference.ProcedureReference.Name;
        Assert.Equal("sp_set_session_context", proc.BaseIdentifier.Value);
        var args = ((ExecutableProcedureReference)exec.ExecuteSpecification.ExecutableEntity).Parameters;
        Assert.Contains(args, a => a.Variable?.Name == "@key" && ((StringLiteral)a.ParameterValue).Value == "TenantId");
        Assert.Contains(args, a => a.Variable?.Name == "@read_only" && ((IntegerLiteral)a.ParameterValue).Value == "1");
        Assert.Contains("SESSION_CONTEXT(N'TenantId')", File.ReadAllText(Paths.Of("sql", "002-rls.sql")));
    }

    static IList<TSqlBatch> Parse_Text(string sql)
    {
        var fragment = new TSql160Parser(true).Parse(new StringReader(sql), out var errors);
        Assert.Empty(errors);
        return ((TSqlScript)fragment).Batches;
    }

    [Fact]
    public void The_verification_script_is_one_rolled_back_transaction_that_covers_both_tenants_none_and_a_cross_tenant_write()
    {
        var text = File.ReadAllText(Paths.Of("sql", "verify-rls.sql"));
        Assert.Equal(1, Regex.Matches(text, @"BEGIN TRANSACTION").Count);
        Assert.EndsWith("ROLLBACK TRANSACTION;", text.TrimEnd());
        Assert.DoesNotMatch(new Regex(@"\bCOMMIT\b", RegexOptions.IgnoreCase), text);
        Assert.Contains("@value = NULL", text);                       // the no-tenant case
        Assert.Contains("BEGIN TRY", text);                           // the cross-tenant write is attempted and reported
        var execs = Find<ExecuteStatement>(Parse("verify-rls.sql"));
        Assert.True(execs.Count >= 6);
    }

    [Fact]
    public void The_app_user_gets_table_rights_only_and_can_never_update_TenantId()
    {
        var batches = Parse("003-grant-app.sql");
        var grants = Find<GrantStatement>(batches);
        var denies = Find<DenyStatement>(batches);
        Assert.All(grants, g => Assert.DoesNotContain(g.Permissions, p => p.Identifiers.Any(i => i.Value.Equals("CONTROL", StringComparison.OrdinalIgnoreCase) || i.Value.Equals("ALTER", StringComparison.OrdinalIgnoreCase))));
        var deny = Assert.Single(denies);
        Assert.Equal("UPDATE", deny.Permissions.Single().Identifiers.Single().Value.ToUpperInvariant());
        Assert.Equal("TenantId", deny.SecurityTargetObject.Columns.Single().Value);
        Assert.Equal("dbo.PurchaseRequests", Table(deny.SecurityTargetObject.ObjectName));
        Assert.Single(Find<CreateUserStatement>(batches));   // from external provider: no password, no login
        Assert.Contains("FROM EXTERNAL PROVIDER", File.ReadAllText(Paths.Of("sql", "003-grant-app.sql")));
    }
}
