using System.Net;
using System.Text;

namespace ProjectRequests.Web.Tests;

/// <summary>The HTTP client the UI uses, against canned API responses (shapes copied from the real API).</summary>
public sealed class RequestsApiClientTests
{
    private sealed class Canned(HttpStatusCode status, string json, string mediaType = "application/json") : HttpMessageHandler
    {
        public HttpRequestMessage? Last { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Last = request;
            return Task.FromResult(new HttpResponseMessage(status) { Content = new StringContent(json, Encoding.UTF8, mediaType) });
        }
    }

    private static (RequestsApiClient Client, Canned Handler) Create(HttpStatusCode status, string json, string mediaType = "application/json")
    {
        var handler = new Canned(status, json, mediaType);
        return (new RequestsApiClient(new HttpClient(handler) { BaseAddress = new Uri("http://localhost:5207/") }), handler);
    }

    private const string Dto = """
        {"id":1,"title":"Laptop refresh","budget":12000,"department":"FIN","requestedBy":"alex.demo@contoso.com",
         "justification":null,"priority":"Standard","status":"Submitted","createdAtUtc":"2026-11-21T05:06:00.06Z",
         "decidedBy":null,"decidedAtUtc":null,"version":"00000000-0000-0000-0000-000000000001"}
        """;

    [Fact]
    public async Task Reads_enums_written_as_strings()
    {
        var (client, handler) = Create(HttpStatusCode.OK, $"[{Dto}]");

        var list = await client.ListAsync(Ct);

        var r = Assert.Single(list);
        Assert.Equal(Priority.Standard, r.Priority);
        Assert.Equal(RequestStatus.Submitted, r.Status);
        Assert.Equal("http://localhost:5207/api/requests", handler.Last!.RequestUri!.ToString());
    }

    [Fact]
    public async Task Not_found_is_null_not_an_exception()
    {
        var (client, _) = Create(HttpStatusCode.NotFound, "");

        Assert.Null(await client.GetAsync(42, Ct));
    }

    [Fact]
    public async Task Validation_problem_keeps_the_field_errors()
    {
        var (client, _) = Create(HttpStatusCode.BadRequest, """
            {"type":"https://tools.ietf.org/html/rfc9110#section-15.5.1","title":"One or more validation errors occurred.",
             "status":400,"errors":{"DepartmentCode":["Unknown department 'HR'."]}}
            """, "application/problem+json");

        var result = await client.CreateAsync(new CreateProjectRequest(), Ct);

        Assert.False(result.Succeeded);
        Assert.Equal("One or more validation errors occurred.", result.Problem);
        Assert.Equal(["Unknown department 'HR'."], result.Errors["DepartmentCode"]);
    }

    [Fact]
    public async Task Conflict_problem_becomes_one_readable_message()
    {
        var (client, handler) = Create(HttpStatusCode.Conflict, """
            {"title":"Request already decided.","status":409,"detail":"Request 1 is Approved."}
            """, "application/problem+json");

        var result = await client.DecideAsync(1, new DecisionRequest { Approve = false, DecidedBy = "sam.approver@contoso.com",
            Version = Guid.Empty }, Ct);

        Assert.Equal("Request already decided. Request 1 is Approved.", result.Problem);
        Assert.Equal("http://localhost:5207/api/requests/1/decision", handler.Last!.RequestUri!.ToString());
    }
}
