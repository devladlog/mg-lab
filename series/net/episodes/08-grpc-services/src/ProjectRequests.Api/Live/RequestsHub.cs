using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using ProjectRequests.Api.Data;

namespace ProjectRequests.Api.Live;

/// <summary>
/// One hub for the live board and the approvers' watcher. Strongly typed: the server can only call the methods
/// declared in <see cref="IRequestsClient"/>.
/// A new hub instance is created for EVERY call, so nothing is stored in fields: per-connection state goes in
/// Context.Items, and group membership is kept by SignalR (in memory, on this server only).
/// </summary>
public sealed class RequestsHub(ILogger<RequestsHub> logger) : Hub<IRequestsClient>
{
    public const string AllGroup = "all";
    private const string GroupKey = "group";

    public static string GroupFor(string departmentCode) => $"dept:{departmentCode.ToUpperInvariant()}";

    /// <summary>
    /// Watch every department (null or empty) or one department. A connection is in exactly one group, so
    /// sending to "all" + "dept:X" never delivers the same event twice.
    /// </summary>
    public async Task<string> Watch(string? department, RequestsDbContext db)   // db: resolved from DI per call
    {
        var group = string.IsNullOrWhiteSpace(department) ? AllGroup : await GroupForKnownAsync(department, db);
        if (Context.Items.TryGetValue(GroupKey, out var old) && old is string previous && previous != group)
            await Groups.RemoveFromGroupAsync(Context.ConnectionId, previous);
        await Groups.AddToGroupAsync(Context.ConnectionId, group);
        Context.Items[GroupKey] = group;            // a new hub instance per call: no state in fields
        logger.LogInformation("Connection {ConnectionId} watches {Group}", Context.ConnectionId, group);
        return group;
    }

    private async Task<string> GroupForKnownAsync(string department, RequestsDbContext db)
    {
        var code = department.Trim().ToUpperInvariant();
        if (!await db.Departments.AnyAsync(d => d.Code == code, Context.ConnectionAborted))
            throw new HubException($"Unknown department '{department}'.");      // HubException: message reaches the client
        return GroupFor(code);
    }

    public override Task OnConnectedAsync()
    {
        logger.LogInformation("Connected: {ConnectionId} ({Transport})", Context.ConnectionId,
            Context.Features.Get<Microsoft.AspNetCore.Http.Connections.Features.IHttpTransportFeature>()?.TransportType);
        return base.OnConnectedAsync();
    }

    public override Task OnDisconnectedAsync(Exception? exception)
    {
        // No RemoveFromGroupAsync needed: SignalR removes a closed connection from its groups.
        logger.LogInformation("Disconnected: {ConnectionId}", Context.ConnectionId);
        return base.OnDisconnectedAsync(exception);
    }
}
