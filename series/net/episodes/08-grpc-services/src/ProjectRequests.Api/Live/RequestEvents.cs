using Microsoft.AspNetCore.SignalR;

namespace ProjectRequests.Api.Live;

/// <summary>What the endpoints tell the outside world after a successful write.</summary>
public interface IRequestEvents
{
    Task CreatedAsync(RequestDto request, CancellationToken ct);
    Task UpdatedAsync(RequestDto request, CancellationToken ct);
}

/// <summary>
/// Pushes events through the hub from OUTSIDE the hub (endpoints, workers): IHubContext, never a hub instance.
/// Best effort on purpose: the database write is already committed, so a push failure is logged, not turned into
/// a 500. SignalR is not a message queue: clients that were offline reload the list when they reconnect.
/// </summary>
public sealed class SignalRRequestEvents(
    IHubContext<RequestsHub, IRequestsClient> hub,
    ILogger<SignalRRequestEvents> logger) : IRequestEvents
{
    public Task CreatedAsync(RequestDto request, CancellationToken ct) =>
        SendAsync(request, "created", c => c.RequestCreated(request));

    public Task UpdatedAsync(RequestDto request, CancellationToken ct) =>
        SendAsync(request, "updated", c => c.RequestUpdated(request));

    private async Task SendAsync(RequestDto request, string what, Func<IRequestsClient, Task> send)
    {
        try
        {
            // Everyone watching all departments + everyone watching this one. Each connection is in one group only.
            await send(hub.Clients.Groups(RequestsHub.AllGroup, RequestsHub.GroupFor(request.Department)));
            logger.LogInformation("Pushed request {Id} {What} to '{All}' and '{Group}'",
                request.Id, what, RequestsHub.AllGroup, RequestsHub.GroupFor(request.Department));
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Could not push request {Id} {What}", request.Id, what);
        }
    }
}
