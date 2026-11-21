using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Azure.Functions.Worker;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace Contoso.InvoiceApproval;

/// <summary>Section "Approval" in configuration.</summary>
public sealed class ApprovalOptions
{
    public string ManagerEmail { get; set; } = "";
    public string FinanceEmail { get; set; } = "";
    public string EscalationEmail { get; set; } = "";
    public decimal FinanceThreshold { get; set; } = 5000m;
    public int StageTimeoutMinutes { get; set; } = 2880;   // two days; the demo uses a few minutes

    public ApprovalSettings ToSettings() =>
        new(ManagerEmail, FinanceEmail, EscalationEmail, FinanceThreshold, checked(StageTimeoutMinutes * 60));
}

public sealed class InvalidInvoiceMessageException(string message) : Exception(message);

public enum IntakeResult { Started, AlreadyRunning, AlreadyFinished, Restarted }

public static partial class InvoiceIntake
{
    [GeneratedRegex("^[a-z0-9]{1,60}\\|[A-Z0-9]{1,40}$")]
    private static partial Regex InvoiceKeyFormat();

    [GeneratedRegex("^[A-Z]{3}$")]
    private static partial Regex CurrencyFormat();

    /// <summary>Same invoice, same instance ID: the instance ID is the idempotency key (Service Bus Basic has no duplicate detection).</summary>
    public static string InstanceIdFor(string invoiceKey) => "invoice-" + invoiceKey.Replace('|', '-');

    public static InvoiceReady Parse(string body)
    {
        InvoiceReady? msg;
        try { msg = JsonSerializer.Deserialize<InvoiceReady>(body, HttpFlowGateway.Json); }
        catch (JsonException e) { throw new InvalidInvoiceMessageException($"Not valid JSON: {e.Message}"); }
        if (msg is null) throw new InvalidInvoiceMessageException("Empty message.");
        if (msg.InvoiceKey is null || !InvoiceKeyFormat().IsMatch(msg.InvoiceKey))
            throw new InvalidInvoiceMessageException("invoiceKey must look like 'vendor|NUMBER' (the episode 1 duplicate key).");
        if (msg.ItemId <= 0) throw new InvalidInvoiceMessageException("itemId must be a SharePoint item ID.");
        if (msg.Total <= 0) throw new InvalidInvoiceMessageException("total must be greater than zero.");
        if (msg.Currency is null || !CurrencyFormat().IsMatch(msg.Currency)) throw new InvalidInvoiceMessageException("currency must be a 3-letter code.");
        if (string.IsNullOrWhiteSpace(msg.SubmittedBy) || !msg.SubmittedBy.Contains('@'))
            throw new InvalidInvoiceMessageException("submittedBy must be an e-mail address.");
        return msg;
    }

    public static async Task<(IntakeResult Result, string InstanceId)> StartAsync(
        DurableTaskClient client, InvoiceReady invoice, ApprovalSettings settings, CancellationToken ct = default)
    {
        var instanceId = InstanceIdFor(invoice.InvoiceKey);
        var existing = await client.GetInstanceAsync(instanceId, getInputsAndOutputs: true, ct);
        var result = IntakeResult.Started;
        if (existing is not null)
        {
            if (existing.RuntimeStatus is OrchestrationRuntimeStatus.Running or OrchestrationRuntimeStatus.Pending
                or OrchestrationRuntimeStatus.Suspended) return (IntakeResult.AlreadyRunning, instanceId);
            // Approved or rejected is final. Only an expired approval may run again (someone resets the status).
            if (existing.RuntimeStatus is OrchestrationRuntimeStatus.Completed
                && existing.ReadOutputAs<ApprovalOutcome>()?.Status != ApprovalStatus.Expired)
                return (IntakeResult.AlreadyFinished, instanceId);
            // Expired, Failed or Terminated: remove the old history and start again with the same ID.
            await client.PurgeInstanceAsync(instanceId, ct);
            result = IntakeResult.Restarted;
        }

        await client.ScheduleNewOrchestrationInstanceAsync(
            InvoiceApprovalOrchestrator.Name, new ApprovalInput(invoice, settings), new StartOrchestrationOptions(instanceId), ct);
        return (result, instanceId);
    }
}

public sealed class InvoiceIntakeFunction(IOptions<ApprovalOptions> approval, ILogger<InvoiceIntakeFunction> log)
{
    [Function("OnInvoiceReady")]
    public async Task Run(
        [ServiceBusTrigger("%InvoiceQueueName%", Connection = "ServiceBus")] string body,
        [DurableClient] DurableTaskClient client,
        CancellationToken ct)
    {
        // An invalid message throws: Service Bus redelivers it and dead-letters it after maxDeliveryCount.
        var invoice = InvoiceIntake.Parse(body);
        var (result, instanceId) = await InvoiceIntake.StartAsync(client, invoice, approval.Value.ToSettings(), ct);
        log.LogInformation("Invoice {InstanceId}: {Result}", instanceId, result);
    }
}
