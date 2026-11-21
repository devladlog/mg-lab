using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.IdentityModel.Tokens;

namespace ExpenseClaims.Api.Tests;

public class ApiTests(ClaimsApiFactory factory) : IClassFixture<ClaimsApiFactory>
{
    private static string NewUser() => "user-" + Guid.NewGuid().ToString("N")[..8];

    private static object ValidClaim(string description = "Train to Porto") => new
    {
        description,
        amount = 48.50m,
        currency = "EUR",
        category = "Travel",
        incurredOn = DateOnly.FromDateTime(DateTime.UtcNow),
    };

    private static async Task<JsonElement> Json(HttpResponseMessage response) =>
        JsonDocument.Parse(await response.Content.ReadAsStringAsync()).RootElement;

    private async Task<int> SubmitAs(string user)
    {
        var response = await factory.ClientFor(user).PostAsJsonAsync("/api/claims", ValidClaim());
        response.EnsureSuccessStatusCode();
        return (await Json(response)).GetProperty("id").GetInt32();
    }

    // ---- authentication -------------------------------------------------------------------

    [Fact]
    public async Task No_token_is_401_with_a_bearer_challenge()
    {
        var response = await factory.CreateClient().GetAsync("/api/claims");
        Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.Equal("Bearer", response.Headers.WwwAuthenticate.Single().Scheme);
    }

    public static TheoryData<string> BadTokens => ["expired", "wrong-audience", "wrong-key"];

    [Theory]
    [MemberData(nameof(BadTokens))]
    public async Task Invalid_tokens_are_401(string kind)
    {
        var token = kind switch
        {
            "expired" => factory.Token("alex", expires: DateTime.UtcNow.AddMinutes(-6)),   // past the 5 min clock skew
            "wrong-audience" => factory.Token("alex", audience: "api://some-other-api"),
            _ => factory.Token("alex", signWith: new SymmetricSecurityKey(RandomNumberGenerator.GetBytes(32))),
        };
        var client = factory.CreateClient();
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);

        Assert.Equal(HttpStatusCode.Unauthorized, (await client.GetAsync("/api/claims")).StatusCode);
    }

    [Fact]
    public async Task Health_endpoint_is_anonymous()
    {
        Assert.Equal("Healthy", await factory.CreateClient().GetStringAsync("/healthz"));
    }

    // ---- [ApiController] behaviour ------------------------------------------------------

    [Fact]
    public async Task Submit_returns_201_with_location_and_the_caller_as_owner()
    {
        var user = NewUser();
        var response = await factory.ClientFor(user).PostAsJsonAsync("/api/claims", ValidClaim());

        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var body = await Json(response);
        Assert.EndsWith($"/api/claims/{body.GetProperty("id").GetInt32()}", response.Headers.Location!.AbsolutePath);
        Assert.Equal(user, body.GetProperty("submittedBy").GetString());
        Assert.Equal("Submitted", body.GetProperty("status").GetString());
    }

    [Fact]
    public async Task Invalid_body_is_an_automatic_400_validation_problem()
    {
        var response = await factory.ClientFor(NewUser()).PostAsJsonAsync("/api/claims",
            new { description = "x", amount = 0, currency = "eur", category = "Party" });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType!.MediaType);
        var errors = (await Json(response)).GetProperty("errors");
        foreach (var field in new[] { "Description", "Amount", "Currency", "Category", "IncurredOn" })
            Assert.True(errors.TryGetProperty(field, out _), $"missing error for {field}");
    }

    [Fact]
    public async Task Future_date_is_rejected_by_the_class_level_rule()
    {
        var response = await factory.ClientFor(NewUser()).PostAsJsonAsync("/api/claims", new
        {
            description = "Taxi", amount = 20, currency = "EUR", category = "Travel",
            incurredOn = DateOnly.FromDateTime(DateTime.UtcNow).AddDays(3),
        });

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("The expense date can't be in the future.",
            (await Json(response)).GetProperty("errors").GetProperty("IncurredOn")[0].GetString());
    }

    [Fact]
    public async Task Unknown_claim_is_404_problem_details()
    {
        var response = await factory.ClientFor(NewUser(), approver: true).GetAsync("/api/claims/987654");
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType!.MediaType);
    }

    // ---- authorization ------------------------------------------------------------------

    [Fact]
    public async Task Employee_cannot_approve_403()
    {
        var id = await SubmitAs(NewUser());
        var response = await factory.ClientFor(NewUser()).PostAsync($"/api/claims/{id}/approve", null);
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task Employee_cannot_read_someone_elses_claim_403()
    {
        var id = await SubmitAs(NewUser());
        var response = await factory.ClientFor(NewUser()).GetAsync($"/api/claims/{id}");
        Assert.Equal(HttpStatusCode.Forbidden, response.StatusCode);
    }

    [Fact]
    public async Task Approver_approves_then_second_approval_is_409()
    {
        var id = await SubmitAs(NewUser());
        var approver = factory.ClientFor(NewUser(), approver: true);

        var first = await approver.PostAsync($"/api/claims/{id}/approve", null);
        Assert.Equal(HttpStatusCode.OK, first.StatusCode);
        Assert.Equal("Approved", (await Json(first)).GetProperty("status").GetString());

        var second = await approver.PostAsync($"/api/claims/{id}/approve", null);
        Assert.Equal(HttpStatusCode.Conflict, second.StatusCode);
        Assert.Equal("Claim already approved.", (await Json(second)).GetProperty("title").GetString());
    }

    [Fact]
    public async Task Approving_your_own_claim_is_409_from_the_exception_handler()
    {
        var sam = NewUser();
        var response = await factory.ClientFor(sam).PostAsJsonAsync("/api/claims", ValidClaim());
        var id = (await Json(response)).GetProperty("id").GetInt32();

        var approve = await factory.ClientFor(sam, approver: true).PostAsync($"/api/claims/{id}/approve", null);
        Assert.Equal(HttpStatusCode.Conflict, approve.StatusCode);
        Assert.Equal("application/problem+json", approve.Content.Headers.ContentType!.MediaType);
        Assert.Equal("You can't approve your own claim.", (await Json(approve)).GetProperty("title").GetString());
    }

    [Fact]
    public async Task Approving_an_unknown_claim_is_404_from_the_exception_handler()
    {
        var response = await factory.ClientFor(NewUser(), approver: true).PostAsync("/api/claims/987654/approve", null);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("There is no claim 987654.", (await Json(response)).GetProperty("detail").GetString());
    }

    [Fact]
    public async Task Employees_list_only_their_own_claims_approvers_see_all()
    {
        var alex = NewUser();
        await SubmitAs(alex);
        await SubmitAs(NewUser());

        var mine = await Json(await factory.ClientFor(alex).GetAsync("/api/claims"));
        Assert.All(mine.EnumerateArray(), c => Assert.Equal(alex, c.GetProperty("submittedBy").GetString()));

        var all = await Json(await factory.ClientFor(NewUser(), approver: true).GetAsync("/api/claims"));
        Assert.True(all.GetArrayLength() > mine.GetArrayLength());
    }

    // ---- rate limiting ------------------------------------------------------------------

    [Fact]
    public async Task Fourth_submit_in_a_minute_is_429_but_other_users_are_not_affected()
    {
        var alex = factory.ClientFor(NewUser());
        for (var i = 0; i < ClaimsApiFactory.SubmitPerMinute; i++)
            Assert.Equal(HttpStatusCode.Created, (await alex.PostAsJsonAsync("/api/claims", ValidClaim())).StatusCode);

        var limited = await alex.PostAsJsonAsync("/api/claims", ValidClaim());
        Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);       // not the default 503
        Assert.True(limited.Headers.RetryAfter is not null);
        Assert.Equal("Too many claims submitted.", (await Json(limited)).GetProperty("title").GetString());

        var kim = factory.ClientFor(NewUser());                                  // own partition
        Assert.Equal(HttpStatusCode.Created, (await kim.PostAsJsonAsync("/api/claims", ValidClaim())).StatusCode);
    }

    [Fact]
    public async Task Invalid_submits_also_count_against_the_limit()
    {
        // The rate limiter runs before model validation, so 400s use up permits too.
        var client = factory.ClientFor(NewUser());
        for (var i = 0; i < ClaimsApiFactory.SubmitPerMinute; i++)
            Assert.Equal(HttpStatusCode.BadRequest, (await client.PostAsJsonAsync("/api/claims", new { })).StatusCode);

        Assert.Equal(HttpStatusCode.TooManyRequests,
            (await client.PostAsJsonAsync("/api/claims", ValidClaim())).StatusCode);
    }

    // ---- OpenAPI ------------------------------------------------------------------------

    [Fact]
    public async Task OpenApi_document_lists_success_and_error_responses()
    {
        var doc = await Json(await factory.CreateClient().GetAsync("/openapi/v1.json"));
        var paths = doc.GetProperty("paths");

        string[] Codes(string path, string method) => paths.GetProperty(path).GetProperty(method)
            .GetProperty("responses").EnumerateObject().Select(p => p.Name).Order().ToArray();

        Assert.Equal(["200", "401"], Codes("/api/claims", "get"));
        Assert.Equal(["201", "400", "401", "429"], Codes("/api/claims", "post"));
        Assert.Equal(["200", "401", "403", "404", "409"], Codes("/api/claims/{id}/approve", "post"));
    }
}
