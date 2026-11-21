using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using PurchaseRequests.Api.Data;
using PurchaseRequests.Api.Endpoints;

namespace PurchaseRequests.Tests;

public static class Requests
{
    public static readonly object Laptop = new { title = "Laptop for new hire", justification = "Starts on Monday in the finance team.", amount = 1450.00m, currency = "EUR" };
    public static readonly object Servers = new { title = "Two lab servers", justification = "Replace the end-of-life lab hosts.", amount = 7500.00m, currency = "EUR" };

    public static async Task<RequestView> Submit(HttpClient client, object body)
    {
        var response = await client.PostAsJsonAsync("/api/requests", body);
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<RequestView>())!;
    }

    public static Task<HttpResponseMessage> Decide(HttpClient client, Guid id, string outcome, string? comment = null) =>
        client.PostAsJsonAsync($"/api/requests/{id}/decision", new { outcome, comment });
}

public class RequestFlowTests
{
    [Fact]
    public async Task Submit_takes_the_owner_from_the_token_and_writes_an_audit_entry()
    {
        using var api = new ApiFactory().Start();
        var created = await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Laptop);

        Assert.Equal("Pending", created.Status);
        Assert.Equal("Alex Demo", created.RequestedByName);
        using var scope = api.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
        var row = await db.PurchaseRequests.SingleAsync();
        Assert.Equal(Ids.Alex, row.RequestedByOid);
        var audit = await db.AuditEntries.SingleAsync();
        Assert.Equal(("Submitted", Ids.Alex, created.Id), (audit.Action, audit.ActorOid, audit.RequestId));
    }

    [Fact]
    public async Task Extra_properties_like_requestedByOid_are_rejected_not_ignored()
    {
        using var api = new ApiFactory().Start();
        var body = new { title = "Laptop", justification = "Needed for the new hire.", amount = 100m, currency = "EUR", requestedByOid = Ids.Sam };
        var response = await api.ClientFor(TestTokens.Alex).PostAsJsonAsync("/api/requests", body);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Theory]
    [InlineData("Hi", "Long enough justification.", 100, "EUR", "title")]
    [InlineData("Laptop", "short", 100, "EUR", "justification")]
    [InlineData("Laptop", "Long enough justification.", 0, "EUR", "amount")]
    [InlineData("Laptop", "Long enough justification.", 50000.01, "EUR", "amount")]
    [InlineData("Laptop", "Long enough justification.", 10.555, "EUR", "amount")]
    [InlineData("Laptop", "Long enough justification.", 100, "USD", "currency")]
    public async Task Invalid_input_is_a_400_problem_with_the_field_name(string title, string justification, double amount, string currency, string field)
    {
        using var api = new ApiFactory().Start();
        var response = await api.ClientFor(TestTokens.Alex).PostAsJsonAsync("/api/requests",
            new { title, justification, amount = (decimal)amount, currency });
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
        using var json = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        Assert.True(json.RootElement.GetProperty("errors").TryGetProperty(field, out _));
    }

    [Fact]
    public async Task Another_requester_gets_404_for_a_request_that_is_not_theirs()
    {
        using var api = new ApiFactory().Start();
        var created = await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Laptop);

        Assert.Equal(HttpStatusCode.NotFound, (await api.ClientFor(TestTokens.Riley).GetAsync($"/api/requests/{created.Id}")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await api.ClientFor(TestTokens.Riley).GetAsync($"/api/requests/{created.Id}/audit")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await api.ClientFor(TestTokens.Alex).GetAsync($"/api/requests/{created.Id}")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await api.ClientFor(TestTokens.Sam).GetAsync($"/api/requests/{created.Id}")).StatusCode);
    }

    [Fact]
    public async Task Mine_lists_only_the_callers_requests()
    {
        using var api = new ApiFactory().Start();
        await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Laptop);
        await Requests.Submit(api.ClientFor(TestTokens.Riley), Requests.Servers);

        var mine = await api.ClientFor(TestTokens.Alex).GetFromJsonAsync<List<RequestView>>("/api/requests/mine");
        Assert.Single(mine!);
        Assert.Equal("Laptop for new hire", mine![0].Title);
    }

    [Fact]
    public async Task Approver_cannot_decide_on_their_own_request_and_the_attempt_is_audited()
    {
        using var api = new ApiFactory().Start();
        var sam = api.ClientFor(TestTokens.Sam);           // Sam is Approver AND Requester
        var own = await Requests.Submit(sam, Requests.Laptop);

        var response = await Requests.Decide(sam, own.Id, "Approve");

        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.Contains("your own request", await response.Content.ReadAsStringAsync());
        var audit = await sam.GetFromJsonAsync<List<AuditView>>($"/api/requests/{own.Id}/audit");
        Assert.Equal(["Submitted", "DecisionDenied"], audit!.Select(a => a.Action));
        var pending = await sam.GetFromJsonAsync<List<RequestView>>("/api/requests/pending");
        Assert.Empty(pending!);                            // own requests aren't offered for decision
    }

    [Fact]
    public async Task Above_the_threshold_an_approver_needs_the_finance_role()
    {
        using var api = new ApiFactory().Start();
        var created = await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Servers);   // 7,500 EUR

        var bySam = await Requests.Decide(api.ClientFor(TestTokens.Sam), created.Id, "Approve");
        Assert.Equal(HttpStatusCode.Forbidden, bySam.StatusCode);
        Assert.Contains("need a finance approver", await bySam.Content.ReadAsStringAsync());

        var byJordan = await Requests.Decide(api.ClientFor(TestTokens.Jordan), created.Id, "Approve", "Budget line 4711.");
        Assert.Equal(HttpStatusCode.OK, byJordan.StatusCode);
        var view = await byJordan.Content.ReadFromJsonAsync<RequestView>();
        Assert.Equal(("Approved", "Jordan Demo"), (view!.Status, view.DecidedByName));
    }

    [Fact]
    public async Task Any_approver_may_reject_above_the_threshold()
    {
        using var api = new ApiFactory().Start();
        var created = await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Servers);
        var response = await Requests.Decide(api.ClientFor(TestTokens.Sam), created.Id, "Reject", "Use the shared lab instead.");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    [Fact]
    public async Task Second_decision_is_409()
    {
        using var api = new ApiFactory().Start();
        var created = await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Laptop);
        Assert.Equal(HttpStatusCode.OK, (await Requests.Decide(api.ClientFor(TestTokens.Sam), created.Id, "Approve")).StatusCode);
        Assert.Equal(HttpStatusCode.Conflict, (await Requests.Decide(api.ClientFor(TestTokens.Jordan), created.Id, "Reject")).StatusCode);
    }

    [Theory]
    [InlineData("approve")]
    [InlineData("0")]
    [InlineData("Escalate")]
    public async Task Outcome_must_be_exactly_Approve_or_Reject(string outcome)
    {
        using var api = new ApiFactory().Start();
        var created = await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Laptop);
        Assert.Equal(HttpStatusCode.BadRequest, (await Requests.Decide(api.ClientFor(TestTokens.Sam), created.Id, outcome)).StatusCode);
    }

    [Fact]
    public async Task Full_story_leaves_a_complete_audit_trail()
    {
        using var api = new ApiFactory().Start();
        var created = await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Servers);
        await Requests.Decide(api.ClientFor(TestTokens.Sam), created.Id, "Approve");          // denied: finance
        await Requests.Decide(api.ClientFor(TestTokens.Jordan), created.Id, "Approve", "OK");

        var audit = await api.ClientFor(TestTokens.Alex).GetFromJsonAsync<List<AuditView>>($"/api/requests/{created.Id}/audit");
        Assert.Equal(new[] { ("Submitted", Ids.Alex), ("DecisionDenied", Ids.Sam), ("Approved", Ids.Jordan) },
            audit!.Select(a => (a.Action, a.ActorOid)));
    }

    [Fact]
    public async Task There_is_no_way_to_change_or_delete_through_the_api()
    {
        using var api = new ApiFactory().Start();
        var client = api.ClientFor(TestTokens.Jordan);
        var created = await Requests.Submit(api.ClientFor(TestTokens.Alex), Requests.Laptop);
        foreach (var method in new[] { HttpMethod.Put, HttpMethod.Delete, HttpMethod.Patch })
        {
            var response = await client.SendAsync(new HttpRequestMessage(method, $"/api/requests/{created.Id}")
            { Content = new StringContent("{}", Encoding.UTF8, "application/json") });
            Assert.Equal(HttpStatusCode.MethodNotAllowed, response.StatusCode);
        }
    }

    [Fact]
    public async Task Writes_are_rate_limited_per_user()
    {
        using var api = new ApiFactory { WritesPerMinute = 2 }.Start();
        var alex = api.ClientFor(TestTokens.Alex);
        await Requests.Submit(alex, Requests.Laptop);
        await Requests.Submit(alex, Requests.Laptop);
        Assert.Equal(HttpStatusCode.TooManyRequests, (await alex.PostAsJsonAsync("/api/requests", Requests.Laptop)).StatusCode);
        // Riley has her own bucket.
        await Requests.Submit(api.ClientFor(TestTokens.Riley), Requests.Laptop);
    }

    [Fact]
    public async Task Responses_are_not_cached_and_not_sniffed()
    {
        using var api = new ApiFactory().Start();
        var response = await api.ClientFor(TestTokens.Alex).GetAsync("/api/requests/mine");
        Assert.Equal("no-store", response.Headers.CacheControl?.ToString());
        Assert.Equal("nosniff", response.Headers.GetValues("X-Content-Type-Options").Single());
    }
}
