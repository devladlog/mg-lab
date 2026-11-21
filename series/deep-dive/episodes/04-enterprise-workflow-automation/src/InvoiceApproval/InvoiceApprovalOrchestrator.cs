using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask;

namespace Contoso.InvoiceApproval;

/// <summary>
/// Multi-stage approval with a deadline and one escalation per stage. Deterministic: time comes from
/// context.CurrentUtcDateTime, IDs from context.NewGuid(), settings from the input, all I/O in activities.
/// </summary>
public sealed class InvoiceApprovalOrchestrator : TaskOrchestrator<ApprovalInput, ApprovalOutcome>
{
    public const string Name = "InvoiceApproval";

    static readonly TaskOptions Retry = TaskOptions.FromRetryPolicy(
        new RetryPolicy(maxNumberOfAttempts: 4, firstRetryInterval: TimeSpan.FromSeconds(10), backoffCoefficient: 2));

    /// <summary>One event name per request: an answer to a replaced request can never complete a newer wait.</summary>
    public static string DecisionEventName(string requestId) => $"Decision-{requestId}";

    public override async Task<ApprovalOutcome> RunAsync(TaskOrchestrationContext context, ApprovalInput input)
    {
        var results = new List<StageResult>();
        foreach (var stage in ApprovalPlan.For(input.Invoice, input.Settings))
        {
            var result = await RunStageAsync(context, input, stage);
            results.Add(result);
            if (result.Status != ApprovalStatus.Approved) break;   // a rejection or an expiry ends the workflow
        }

        var status = results[^1].Status;
        var summary = string.Join("; ", results.Select(r =>
            $"{r.Stage}: {r.Status}{(r.DecidedBy is null ? "" : $" by {r.DecidedBy}")}{(r.Attempts > 1 ? " (escalated)" : "")}"));
        var outcome = new ApprovalOutcome(context.InstanceId, input.Invoice, status, results, summary);

        context.SetCustomStatus(null);
        await context.CallActivityAsync(ApprovalActivities.RecordOutcome, outcome, Retry);
        return outcome;
    }

    static async Task<StageResult> RunStageAsync(TaskOrchestrationContext context, ApprovalInput input, Stage stage)
    {
        var approver = stage.Approver;
        const int maxAttempts = 2;                 // first approver, then one escalation
        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            var requestId = context.NewGuid().ToString("N");
            var due = context.CurrentUtcDateTime.AddSeconds(input.Settings.StageTimeoutSeconds);

            // Status first, then the request: both are committed at the same checkpoint, so the decision
            // endpoint already knows this request when the approver can see it.
            context.SetCustomStatus(new PendingApproval(stage.Name, requestId, approver, attempt, due));
            await context.CallActivityAsync(ApprovalActivities.SendApprovalRequest,
                new ApprovalRequest(context.InstanceId, requestId, stage.Name, approver, attempt, due, input.Invoice), Retry);

            using var timeoutCts = new CancellationTokenSource();
            Task timeout = context.CreateTimer(due, timeoutCts.Token);
            Task<DecisionEvent> decision = context.WaitForExternalEvent<DecisionEvent>(DecisionEventName(requestId));

            if (await Task.WhenAny(decision, timeout) == decision)
            {
                timeoutCts.Cancel();   // don't leave a timer behind
                var d = decision.Result;
                var status = d.Outcome == "Approve" ? ApprovalStatus.Approved : ApprovalStatus.Rejected;
                return new StageResult(stage.Name, status, d.Responder, d.Comments, attempt);
            }

            if (stage.EscalateTo is null || attempt == maxAttempts)
                return new StageResult(stage.Name, ApprovalStatus.Expired, null, null, attempt);

            approver = stage.EscalateTo;   // nobody answered in time: ask the escalation approver
        }
        throw new InvalidOperationException("Unreachable: the last attempt always returns.");
    }
}

public static class InvoiceApprovalFunctions
{
    [Function(InvoiceApprovalOrchestrator.Name)]
    public static Task<ApprovalOutcome> Run([OrchestrationTrigger] TaskOrchestrationContext context, ApprovalInput input) =>
        new InvoiceApprovalOrchestrator().RunAsync(context, input);
}
