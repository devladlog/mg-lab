using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;

namespace Contoso.InvoiceApproval;

public sealed record DecisionBody(string? Outcome, string? Responder, string? Comments);

public sealed record DecisionReply(int StatusCode, string Message);

public static class DecisionHandler
{
    public static async Task<DecisionReply> HandleAsync(DurableTaskClient client, CallbackSigner signer,
        string instanceId, string requestId, string? signature, DecisionBody? body, CancellationToken ct = default)
    {
        if (!signer.Verify(instanceId, requestId, signature))
            return new(StatusCodes.Status401Unauthorized, "Invalid or missing signature.");
        if (body is null || body.Outcome is not ("Approve" or "Reject") || string.IsNullOrWhiteSpace(body.Responder))
            return new(StatusCodes.Status400BadRequest, "Body must have outcome (Approve or Reject) and responder.");
        if (body.Comments is { Length: > 1000 })
            return new(StatusCodes.Status400BadRequest, "Comments can be at most 1000 characters.");

        var instance = await client.GetInstanceAsync(instanceId, getInputsAndOutputs: true, ct);
        if (instance is null)
            return new(StatusCodes.Status404NotFound, "No such approval.");
        if (instance.RuntimeStatus != OrchestrationRuntimeStatus.Running)
            return new(StatusCodes.Status409Conflict, "This approval is already finished.");

        var pending = instance.SerializedCustomStatus is null ? null : instance.ReadCustomStatusAs<PendingApproval>();
        if (pending is null || pending.RequestId != requestId)
            return new(StatusCodes.Status409Conflict, "This approval request is no longer active: it was escalated or already answered.");
        if (!string.Equals(pending.Approver, body.Responder.Trim(), StringComparison.OrdinalIgnoreCase))
            return new(StatusCodes.Status403Forbidden, $"Only the assigned approver can answer this request.");

        await client.RaiseEventAsync(instanceId, InvoiceApprovalOrchestrator.DecisionEventName(requestId),
            new DecisionEvent(body.Outcome, body.Responder.Trim(), body.Comments?.Trim()), ct);
        return new(StatusCodes.Status202Accepted, "Decision recorded.");
    }
}

public sealed class DecisionFunction(CallbackSigner signer, ILogger<DecisionFunction> log)
{
    const int MaxBodyBytes = 16 * 1024;

    /// <summary>Anonymous at the Functions level on purpose: the per-request HMAC in ?sig= is the credential.</summary>
    [Function("SubmitDecision")]
    public async Task<IActionResult> Run(
        [HttpTrigger(AuthorizationLevel.Anonymous, "post", Route = "approvals/{instanceId}/{requestId}/decision")] HttpRequest req,
        [DurableClient] DurableTaskClient client,
        string instanceId, string requestId, CancellationToken ct)
    {
        if (req.ContentLength is > MaxBodyBytes)
            return new ObjectResult(new { message = "Body too large." }) { StatusCode = StatusCodes.Status413PayloadTooLarge };

        DecisionBody? body;
        try { body = await JsonSerializer.DeserializeAsync<DecisionBody>(req.Body, HttpFlowGateway.Json, ct); }
        catch (JsonException) { body = null; }

        var reply = await DecisionHandler.HandleAsync(client, signer, instanceId, requestId, req.Query["sig"], body, ct);
        log.LogInformation("Decision for {InstanceId}/{RequestId}: {Status}", instanceId, requestId, reply.StatusCode);
        return new ObjectResult(new { message = reply.Message }) { StatusCode = reply.StatusCode };
    }
}
