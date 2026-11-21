using System.Collections.Concurrent;
using System.Web;
using Contoso.InvoiceApproval;
using Microsoft.DurableTask;
using Microsoft.DurableTask.Client;
using Microsoft.DurableTask.Testing;
using Microsoft.Extensions.Options;

namespace InvoiceApproval.Tests;

/// <summary>Fictional people of the series (lab users).</summary>
public static class People
{
    public const string Alex = "alex.demo@contoso.com";     // accounts payable clerk, uploads invoices
    public const string Sam = "sam.demo@contoso.com";       // manager
    public const string Jordan = "jordan.demo@contoso.com"; // finance director
    public const string Riley = "riley.demo@contoso.com";   // escalation (CFO office)
}

/// <summary>Stands in for the Power Automate relay flow: keeps every message the orchestration sends.</summary>
public sealed class FakeFlow : IFlowGateway
{
    public ConcurrentQueue<FlowMessage> Messages { get; } = new();

    public Task PostAsync(FlowMessage message, CancellationToken ct = default)
    {
        Messages.Enqueue(message);
        return Task.CompletedTask;
    }

    public List<FlowMessage> Requests => Messages.Where(m => m.Kind == FlowMessage.ApprovalRequestKind).ToList();
    public List<FlowMessage> Outcomes => Messages.Where(m => m.Kind == FlowMessage.OutcomeKind).ToList();
}

/// <summary>
/// The real orchestrator and the real activity code running on the in-memory Durable Task engine
/// (DurableTaskTestHost: real timers, real external events, real replay). Only the flow is fake.
/// </summary>
public sealed class TestWorld : IAsyncDisposable
{
    public static readonly byte[] Key = Enumerable.Range(1, 32).Select(i => (byte)i).ToArray();
    public static readonly Uri BaseUrl = new("https://func-invoices-test.azurewebsites.net/");

    public FakeFlow Flow { get; } = new();
    public CallbackSigner Signer { get; } = new(Key);
    public DurableTaskTestHost Host { get; private set; } = null!;
    public DurableTaskClient Client => Host.Client;

    public static ApprovalSettings Settings(int timeoutSeconds = 60) =>
        new(People.Sam, People.Jordan, People.Riley, FinanceThreshold: 5000m, StageTimeoutSeconds: timeoutSeconds);

    public static InvoiceReady Invoice(decimal total = 1476m, string number = "INV1001", string submittedBy = People.Alex) =>
        new($"fabrikam|{number}", ItemId: 7, "Fabrikam Ltd", number, total, "EUR", submittedBy,
            "https://contoso.sharepoint.com/sites/finance-lab/Invoices%20Inbox/fabrikam-clean.pdf");

    public static async Task<TestWorld> StartAsync()
    {
        var world = new TestWorld();
        var activities = new ApprovalActivities(world.Flow, world.Signer,
            Options.Create(new CallbackOptions { BaseUrl = BaseUrl.ToString() }));
        world.Host = await DurableTaskTestHost.StartAsync(tasks =>
        {
            // Same name and same body as the [Function] wrapper in InvoiceApprovalFunctions.
            tasks.AddOrchestratorFunc<ApprovalInput, ApprovalOutcome>(InvoiceApprovalOrchestrator.Name,
                (ctx, input) => new InvoiceApprovalOrchestrator().RunAsync(ctx, input));
            tasks.AddActivityFunc<ApprovalRequest>(ApprovalActivities.SendApprovalRequest,
                (_, r) => activities.SendApprovalRequestAsync(r));
            tasks.AddActivityFunc<ApprovalOutcome>(ApprovalActivities.RecordOutcome,
                (_, o) => activities.RecordOutcomeAsync(o));
        });
        return world;
    }

    public async Task<string> StartApprovalAsync(InvoiceReady invoice, ApprovalSettings settings)
    {
        var (result, id) = await InvoiceIntake.StartAsync(Client, invoice, settings);
        Assert.Equal(IntakeResult.Started, result);
        return id;
    }

    /// <summary>Wait until the flow has received <paramref name="count"/> approval requests.</summary>
    public async Task<FlowMessage> WaitForRequestAsync(int count, TimeSpan? within = null)
    {
        var until = DateTime.UtcNow + (within ?? TimeSpan.FromSeconds(20));
        while (DateTime.UtcNow < until)
        {
            var requests = Flow.Requests;
            if (requests.Count >= count) return requests[count - 1];
            await Task.Delay(50);
        }
        throw new TimeoutException($"The flow never received approval request #{count}.");
    }

    /// <summary>Do what the relay flow does after "Start and wait for an approval": POST to the callback URL.</summary>
    public Task<DecisionReply> AnswerAsync(FlowMessage request, string outcome, string responder, string? comments = null)
    {
        var (instanceId, requestId, sig) = ParseCallback(request.CallbackUrl!);
        return DecisionHandler.HandleAsync(Client, Signer, instanceId, requestId, sig, new DecisionBody(outcome, responder, comments));
    }

    public static (string InstanceId, string RequestId, string? Sig) ParseCallback(string url)
    {
        var uri = new Uri(url);
        var segments = uri.AbsolutePath.Split('/', StringSplitOptions.RemoveEmptyEntries); // api, approvals, {id}, {req}, decision
        return (Uri.UnescapeDataString(segments[2]), segments[3], HttpUtility.ParseQueryString(uri.Query)["sig"]);
    }

    public async Task<ApprovalOutcome> WaitForOutcomeAsync(string instanceId, TimeSpan? within = null)
    {
        using var cts = new CancellationTokenSource(within ?? TimeSpan.FromSeconds(30));
        var meta = await Client.WaitForInstanceCompletionAsync(instanceId, getInputsAndOutputs: true, cts.Token);
        Assert.Equal(OrchestrationRuntimeStatus.Completed, meta.RuntimeStatus);
        return meta.ReadOutputAs<ApprovalOutcome>()!;
    }

    public async ValueTask DisposeAsync() => await Host.DisposeAsync();
}
