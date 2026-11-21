using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Azure.Core;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Options;

namespace Contoso.InvoiceApproval;

/// <summary>Section "Callback": where the flow sends the decision back to.</summary>
public sealed class CallbackOptions
{
    public string BaseUrl { get; set; } = "";       // https://<function app>.azurewebsites.net/
    public string SigningKey { get; set; } = "";    // base64, from Key Vault
}

/// <summary>Section "Flow": the "Invoice approval relay" HTTP trigger.</summary>
public sealed class FlowOptions
{
    public string Url { get; set; } = "";
    /// <summary>
    /// If set, call the trigger with a Microsoft Entra token for this audience (trigger set to "Specific users in my
    /// tenant" with the function's managed identity). Empty: the URL's own SAS signature is the credential.
    /// </summary>
    public string Audience { get; set; } = "";

    /// <summary>"https://service.flow.microsoft.com/" + "/.default" keeps the trailing slash in the token audience.</summary>
    public string Scope => Audience + "/.default";
}

public interface IFlowGateway
{
    Task PostAsync(FlowMessage message, CancellationToken ct = default);
}

public sealed class HttpFlowGateway(HttpClient http, IOptions<FlowOptions> options, TokenCredential credential) : IFlowGateway
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public async Task PostAsync(FlowMessage message, CancellationToken ct = default)
    {
        var o = options.Value;
        using var request = new HttpRequestMessage(HttpMethod.Post, o.Url) { Content = JsonContent.Create(message, options: Json) };
        if (!string.IsNullOrEmpty(o.Audience))
        {
            var token = await credential.GetTokenAsync(new TokenRequestContext([o.Scope]), ct);
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
        }
        using var response = await http.SendAsync(request, ct);
        // Throwing lets the orchestrator's retry policy try again; the response body is not logged (may echo data).
        if (!response.IsSuccessStatusCode)
            throw new HttpRequestException($"Approval flow answered {(int)response.StatusCode}.", null, response.StatusCode);
    }
}

public sealed class ApprovalActivities(IFlowGateway flow, CallbackSigner signer, IOptions<CallbackOptions> callback)
{
    public const string SendApprovalRequest = nameof(SendApprovalRequest);
    public const string RecordOutcome = nameof(RecordOutcome);

    [Function(SendApprovalRequest)]
    public async Task SendApprovalRequestAsync([ActivityTrigger] ApprovalRequest r)
    {
        var url = signer.CallbackUrl(new Uri(callback.Value.BaseUrl), r.InstanceId, r.RequestId);
        await flow.PostAsync(Base(r.InstanceId, r.Invoice) with
        {
            Kind = FlowMessage.ApprovalRequestKind,
            Status = ApprovalStatus.Waiting,
            StatusText = r.Attempt == 1 ? $"{r.Stage} approval: {r.Approver}" : $"{r.Stage} approval escalated to {r.Approver}",
            ApproverEmail = r.Approver,
            Stage = r.Stage,
            DueUtc = r.DueUtc,
            CallbackUrl = url.ToString(),
        });
    }

    [Function(RecordOutcome)]
    public async Task RecordOutcomeAsync([ActivityTrigger] ApprovalOutcome o)
    {
        var last = o.Stages[^1];
        await flow.PostAsync(Base(o.InstanceId, o.Invoice) with
        {
            Kind = FlowMessage.OutcomeKind,
            Status = o.Status,
            StatusText = o.Summary,
            DecidedBy = last.DecidedBy,
        });
    }

    static FlowMessage Base(string instanceId, InvoiceReady i) => new()
    {
        Kind = "",
        InstanceId = instanceId,
        ItemId = i.ItemId,
        Vendor = i.Vendor,
        InvoiceNumber = i.InvoiceNumber,
        Total = i.Total,
        Currency = i.Currency,
        FileUrl = i.FileUrl,
        SubmittedBy = i.SubmittedBy,
        Status = "",
        StatusText = "",
    };
}
