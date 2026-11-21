using System.Net;
using System.Text.Json;
using Azure.Core;
using Contoso.InvoiceApproval;
using Microsoft.Extensions.Options;

namespace InvoiceApproval.Tests;

public class ApprovalPlanTests
{
    [Fact]
    public void Up_to_the_threshold_one_stage_with_escalation()
    {
        var stage = Assert.Single(ApprovalPlan.For(TestWorld.Invoice(total: 5000m), TestWorld.Settings()));
        Assert.Equal(new Stage("Manager", People.Sam, People.Riley), stage);
    }

    [Fact]
    public void Above_the_threshold_manager_then_finance() =>
        Assert.Equal(["Manager", "Finance"], ApprovalPlan.For(TestWorld.Invoice(total: 5000.01m), TestWorld.Settings()).Select(s => s.Name));

    [Fact]
    public void The_submitter_never_approves_their_own_invoice()
    {
        var stages = ApprovalPlan.For(TestWorld.Invoice(total: 9000m, submittedBy: "SAM.demo@contoso.com"), TestWorld.Settings());
        Assert.Equal(new Stage("Manager", People.Riley, null), stages[0]);   // straight to escalation, no further escalation
        Assert.Equal(People.Jordan, stages[1].Approver);
    }
}

public class IntakeParsingTests
{
    const string Valid = """
        {"invoiceKey":"fabrikam|INV1001","itemId":7,"vendor":"Fabrikam Ltd","invoiceNumber":"INV1001","total":1476.00,
         "currency":"EUR","submittedBy":"alex.demo@contoso.com","fileUrl":"https://contoso.sharepoint.com/x.pdf"}
        """;

    [Fact]
    public void Parses_the_message_the_flow_sends()
    {
        var invoice = InvoiceIntake.Parse(Valid);
        Assert.Equal(("fabrikam|INV1001", 7, 1476.00m), (invoice.InvoiceKey, invoice.ItemId, invoice.Total));
        Assert.Equal("invoice-fabrikam-INV1001", InvoiceIntake.InstanceIdFor(invoice.InvoiceKey));
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("null")]
    [InlineData("""{"invoiceKey":"fabrikam/INV1","itemId":7,"total":1,"currency":"EUR","submittedBy":"a@b"}""")]
    [InlineData("""{"invoiceKey":"fabrikam|INV1","itemId":0,"total":1,"currency":"EUR","submittedBy":"a@b"}""")]
    [InlineData("""{"invoiceKey":"fabrikam|INV1","itemId":7,"total":-5,"currency":"EUR","submittedBy":"a@b"}""")]
    [InlineData("""{"invoiceKey":"fabrikam|INV1","itemId":7,"total":1,"currency":"€","submittedBy":"a@b"}""")]
    [InlineData("""{"invoiceKey":"fabrikam|INV1","itemId":7,"total":1,"currency":"EUR","submittedBy":"alex"}""")]
    public void Invalid_messages_throw_so_service_bus_can_dead_letter_them(string body) =>
        Assert.Throws<InvalidInvoiceMessageException>(() => InvoiceIntake.Parse(body));

    [Fact]
    public void Stage_timeout_minutes_become_seconds_in_the_orchestration_input() =>
        Assert.Equal(300, new ApprovalOptions { StageTimeoutMinutes = 5 }.ToSettings().StageTimeoutSeconds);
}

public class CallbackSignerTests
{
    readonly CallbackSigner _signer = new(TestWorld.Key);

    [Fact]
    public void Signature_verifies_only_for_the_same_instance_and_request()
    {
        var sig = _signer.Sign("invoice-fabrikam-INV1001", "r1");
        Assert.True(_signer.Verify("invoice-fabrikam-INV1001", "r1", sig));
        Assert.False(_signer.Verify("invoice-fabrikam-INV1001", "r2", sig));
        Assert.False(_signer.Verify("invoice-fabrikam-INV1002", "r1", sig));
        Assert.False(_signer.Verify("invoice-fabrikam-INV1001", "r1", sig[..^1] + (sig[^1] == 'A' ? 'B' : 'A')));
    }

    [Fact]
    public void Url_is_url_safe_and_points_at_the_decision_route()
    {
        var url = _signer.CallbackUrl(TestWorld.BaseUrl, "invoice-fabrikam-INV1001", "abc");
        Assert.StartsWith("https://func-invoices-test.azurewebsites.net/api/approvals/invoice-fabrikam-INV1001/abc/decision?sig=", url.ToString());
        Assert.DoesNotContain('+', url.Query);
        Assert.DoesNotContain('/', url.Query);
    }

    [Fact]
    public void Short_keys_are_refused() => Assert.Throws<ArgumentException>(() => new CallbackSigner(new byte[16]));

    [Fact]
    public void Missing_key_setting_fails_at_startup() => Assert.Throws<InvalidOperationException>(() => CallbackSigner.FromBase64(""));
}

public class FlowGatewayTests
{
    sealed class CapturingHandler(HttpStatusCode status) : HttpMessageHandler
    {
        public HttpRequestMessage? Request;
        public string? Body;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Request = request;
            Body = await request.Content!.ReadAsStringAsync(ct);
            return new HttpResponseMessage(status);
        }
    }

    sealed class FakeCredential : TokenCredential
    {
        public string[]? Scopes;
        public override AccessToken GetToken(TokenRequestContext ctx, CancellationToken ct) => throw new NotSupportedException();
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext ctx, CancellationToken ct)
        {
            Scopes = ctx.Scopes;
            return ValueTask.FromResult(new AccessToken("fake-token", DateTimeOffset.UtcNow.AddHours(1)));
        }
    }

    static readonly FlowMessage Message = new()
    {
        Kind = FlowMessage.OutcomeKind, InstanceId = "invoice-fabrikam-INV1001", ItemId = 7, Vendor = "Fabrikam Ltd",
        InvoiceNumber = "INV1001", Total = 1476m, Currency = "EUR", FileUrl = "https://contoso.sharepoint.com/x.pdf",
        SubmittedBy = People.Alex, Status = ApprovalStatus.Approved, StatusText = "Manager: Approved by sam.demo@contoso.com",
        DecidedBy = People.Sam,
    };

    static (HttpFlowGateway, CapturingHandler, FakeCredential) Make(string audience, HttpStatusCode status = HttpStatusCode.Accepted)
    {
        var handler = new CapturingHandler(status);
        var credential = new FakeCredential();
        var options = Options.Create(new FlowOptions { Url = "https://prod-00.westeurope.logic.azure.com/workflows/x/triggers/manual/paths/invoke", Audience = audience });
        return (new HttpFlowGateway(new HttpClient(handler), options, credential), handler, credential);
    }

    [Fact]
    public async Task With_an_audience_it_sends_a_managed_identity_token_and_keeps_the_trailing_slash()
    {
        var (gateway, handler, credential) = Make("https://service.flow.microsoft.com/");
        await gateway.PostAsync(Message);
        Assert.Equal(["https://service.flow.microsoft.com//.default"], credential.Scopes!);
        Assert.Equal(("Bearer", "fake-token"), (handler.Request!.Headers.Authorization!.Scheme, handler.Request.Headers.Authorization.Parameter));
    }

    [Fact]
    public async Task Without_an_audience_there_is_no_authorization_header()
    {
        var (gateway, handler, credential) = Make("");
        await gateway.PostAsync(Message);
        Assert.Null(handler.Request!.Headers.Authorization);
        Assert.Null(credential.Scopes);
    }

    [Fact]
    public async Task Body_is_camelCase_and_omits_empty_optional_fields()
    {
        var (gateway, handler, _) = Make("");
        await gateway.PostAsync(Message);
        using var json = JsonDocument.Parse(handler.Body!);
        Assert.Equal("outcome", json.RootElement.GetProperty("kind").GetString());
        Assert.Equal(7, json.RootElement.GetProperty("itemId").GetInt32());
        Assert.False(json.RootElement.TryGetProperty("callbackUrl", out _));
    }

    [Fact]
    public async Task A_failed_call_throws_so_the_orchestrator_retries()
    {
        var (gateway, _, _) = Make("", HttpStatusCode.TooManyRequests);
        var e = await Assert.ThrowsAsync<HttpRequestException>(() => gateway.PostAsync(Message));
        Assert.Equal(HttpStatusCode.TooManyRequests, e.StatusCode);
    }
}
