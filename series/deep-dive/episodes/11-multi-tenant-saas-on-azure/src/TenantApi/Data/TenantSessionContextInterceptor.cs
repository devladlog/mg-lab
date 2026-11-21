using System.Data.Common;
using Microsoft.EntityFrameworkCore.Diagnostics;

namespace TenantApi.Data;

/// <summary>
/// Hands the tenant to SQL Server's row-level security. Right after a connection opens it stores the tenant in
/// SESSION_CONTEXT with @read_only = 1, so nothing later on that connection can change it until the connection
/// goes back to the pool. The policy in sql/002-rls.sql reads it. With no tenant, nothing is set and the policy
/// returns no rows.
/// Stateless on purpose: one shared instance for every context. (A new interceptor instance per scope would make
/// EF Core build a new internal service provider per request.) The tenant comes from the context that opened the connection.
/// </summary>
public sealed class TenantSessionContextInterceptor(string commandText = TenantSessionContextInterceptor.SetSessionContextSql)
    : DbConnectionInterceptor
{
    public const string SetSessionContextSql =
        "EXEC sys.sp_set_session_context @key = N'TenantId', @value = @tenant, @read_only = 1;";

    public static readonly TenantSessionContextInterceptor Shared = new();

    public override void ConnectionOpened(DbConnection connection, ConnectionEndEventData eventData)
    {
        using var cmd = Build(connection, eventData);
        cmd?.ExecuteNonQuery();
    }

    public override async Task ConnectionOpenedAsync(DbConnection connection, ConnectionEndEventData eventData, CancellationToken cancellationToken = default)
    {
        await using var cmd = Build(connection, eventData);
        if (cmd is not null) await cmd.ExecuteNonQueryAsync(cancellationToken);
    }

    DbCommand? Build(DbConnection connection, ConnectionEndEventData eventData)
    {
        if (eventData.Context is not AppDbContext { CurrentTenantId: var tenantId } || tenantId == Guid.Empty) return null;
        var cmd = connection.CreateCommand();
        cmd.CommandText = commandText;
        var p = cmd.CreateParameter();
        p.ParameterName = "@tenant";
        p.Value = tenantId;
        cmd.Parameters.Add(p);
        return cmd;
    }
}
