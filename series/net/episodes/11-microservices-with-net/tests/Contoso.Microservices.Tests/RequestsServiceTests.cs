using System.Net;
using System.Net.Http.Json;
using Contoso.Budget.Service;
using Contoso.Requests.Service.Requests;
using Microsoft.Extensions.DependencyInjection;

namespace Contoso.Microservices.Tests;

public class RequestsServiceTests
{
    private static async Task<BudgetStatus> BudgetOf(Lab lab, string department) =>
        (await lab.BudgetHttp.GetFromJsonAsync<BudgetStatus>($"/api/budgets/{department}"))!;

    [Fact]
    public async Task A_new_request_reserves_budget_in_the_other_service()
    {
        using var lab = new Lab();
        var response = await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest());
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var dto = (await response.Content.ReadFromJsonAsync<RequestDto>())!;
        Assert.Equal("Reserved", dto.BudgetState);
        Assert.Equal("FIN", dto.Department);
        Assert.Equal(12_000m, (await BudgetOf(lab, "FIN")).Reserved);
        Assert.Equal(1, lab.BudgetWire.Attempts);
    }

    [Fact]
    public async Task A_request_over_the_department_budget_is_saved_as_declined()
    {
        using var lab = new Lab();
        var dto = (await (await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest("IT", 40_000m)))
            .Content.ReadFromJsonAsync<RequestDto>())!;
        Assert.Equal("Declined", dto.BudgetState);
        Assert.Equal(0m, (await BudgetOf(lab, "IT")).Reserved);
    }

    [Fact]
    public async Task Transient_failures_of_the_budget_service_are_retried_and_the_caller_never_notices()
    {
        using var lab = new Lab(failFirstAttempts: 2);          // two 503s before anything happens, then fine
        var response = await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest());
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        Assert.Equal("Reserved", (await response.Content.ReadFromJsonAsync<RequestDto>())!.BudgetState);
        Assert.Equal(3, lab.BudgetWire.Attempts);               // 1 try + 2 retries
    }

    [Fact]
    public async Task Lost_answers_are_retried_without_reserving_twice()
    {
        using var lab = new Lab(failFirstAttempts: 2, failAfterCommit: true);   // the money IS reserved, the answer is lost, twice
        var response = await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest());
        Assert.Equal("Reserved", (await response.Content.ReadFromJsonAsync<RequestDto>())!.BudgetState);
        Assert.Equal(3, lab.BudgetWire.Attempts);
        Assert.Equal(12_000m, (await BudgetOf(lab, "FIN")).Reserved);           // once, not 36,000
    }

    [Fact]
    public async Task When_the_budget_service_is_down_the_request_is_kept_as_pending_and_the_service_stays_healthy()
    {
        using var lab = new Lab();
        lab.BudgetWire.Down = true;
        var response = await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest());
        Assert.Equal(HttpStatusCode.Accepted, response.StatusCode);
        var dto = (await response.Content.ReadFromJsonAsync<RequestDto>())!;
        Assert.Equal("Pending", dto.BudgetState);
        Assert.Equal(4, lab.BudgetWire.Attempts);               // 1 try + 3 retries, then it gives up

        Assert.Equal(HttpStatusCode.OK, (await lab.RequestsHttp.GetAsync($"/api/requests/{dto.Id}")).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await lab.RequestsHttp.GetAsync("/health")).StatusCode);   // Budget is not a readiness dependency
    }

    [Fact]
    public async Task After_a_few_failures_the_circuit_opens_and_calls_fail_fast()
    {
        using var lab = new Lab(breakerMinimumThroughput: 2);
        lab.BudgetWire.Down = true;

        await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest());
        var afterFirst = lab.BudgetWire.Attempts;
        var second = await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest(title: "Second request"));

        Assert.True(afterFirst < 4, $"the breaker should have cut the retries short, saw {afterFirst} attempts");
        Assert.Equal(afterFirst, lab.BudgetWire.Attempts);       // the second call never touched the wire
        Assert.Equal(HttpStatusCode.Accepted, second.StatusCode);
    }

    [Fact]
    public async Task The_recheck_finishes_pending_requests_once_the_budget_service_is_back()
    {
        using var lab = new Lab(breakerMinimumThroughput: 1000);   // keep the breaker out of this one
        lab.BudgetWire.Down = true;
        var dto = (await (await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest()))
            .Content.ReadFromJsonAsync<RequestDto>())!;
        var rechecker = lab.Requests.Services.GetRequiredService<BudgetRechecker>();

        Assert.Equal(0, await rechecker.RunOnceAsync(CancellationToken.None));      // still down: nothing changes
        Assert.Equal(0m, (await BudgetOf(lab, "FIN")).Reserved);

        lab.BudgetWire.Down = false;
        Assert.Equal(1, await rechecker.RunOnceAsync(CancellationToken.None));
        var done = (await lab.RequestsHttp.GetFromJsonAsync<RequestDto>($"/api/requests/{dto.Id}"))!;
        Assert.Equal("Reserved", done.BudgetState);
        Assert.Equal(12_000m, (await BudgetOf(lab, "FIN")).Reserved);
        Assert.Equal(0, await rechecker.RunOnceAsync(CancellationToken.None));     // nothing left to do
    }

    [Fact]
    public async Task The_circuit_lets_a_probe_through_after_the_break_and_closes_again_when_the_service_is_back()
    {
        using var lab = new Lab(breakerMinimumThroughput: 2, breakSeconds: 1);
        lab.BudgetWire.Down = true;
        var dto = (await (await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest()))
            .Content.ReadFromJsonAsync<RequestDto>())!;
        var rechecker = lab.Requests.Services.GetRequiredService<BudgetRechecker>();

        lab.BudgetWire.Down = false;
        Assert.Equal(0, await rechecker.RunOnceAsync(CancellationToken.None));   // service is back, but the circuit is still open
        await Task.Delay(TimeSpan.FromSeconds(1.5));                              // break duration over: half-open
        Assert.Equal(1, await rechecker.RunOnceAsync(CancellationToken.None));   // the probe succeeds, the circuit closes
        Assert.Equal("Reserved", (await lab.RequestsHttp.GetFromJsonAsync<RequestDto>($"/api/requests/{dto.Id}"))!.BudgetState);
    }

    [Fact]
    public async Task The_same_idempotency_key_creates_one_request_and_reserves_once()
    {
        using var lab = new Lab();
        var key = Guid.NewGuid().ToString();
        HttpRequestMessage Post() => new(HttpMethod.Post, "/api/requests")
        { Content = JsonContent.Create(Lab.NewRequest()), Headers = { { "Idempotency-Key", key } } };

        var first = await lab.RequestsHttp.SendAsync(Post());
        var second = await lab.RequestsHttp.SendAsync(Post());

        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(HttpStatusCode.OK, second.StatusCode);
        Assert.Equal("true", second.Headers.GetValues("Idempotent-Replayed").Single());
        Assert.Equal((await first.Content.ReadFromJsonAsync<RequestDto>())!.Id, (await second.Content.ReadFromJsonAsync<RequestDto>())!.Id);
        Assert.Single((await lab.RequestsHttp.GetFromJsonAsync<List<RequestDto>>("/api/requests"))!);
        Assert.Equal(12_000m, (await BudgetOf(lab, "FIN")).Reserved);
    }

    [Fact]
    public async Task Eight_parallel_posts_with_one_key_create_one_request()
    {
        using var lab = new Lab();
        var key = Guid.NewGuid().ToString();
        var responses = await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => Task.Run(() =>
            lab.RequestsHttp.SendAsync(new HttpRequestMessage(HttpMethod.Post, "/api/requests")
            { Content = JsonContent.Create(Lab.NewRequest()), Headers = { { "Idempotency-Key", key } } }))));
        Assert.All(responses, r => Assert.True(r.IsSuccessStatusCode, r.StatusCode.ToString()));
        Assert.Single((await lab.RequestsHttp.GetFromJsonAsync<List<RequestDto>>("/api/requests"))!);
        Assert.Equal(12_000m, (await BudgetOf(lab, "FIN")).Reserved);
    }

    [Fact]
    public async Task Bad_input_is_a_400_and_a_missing_request_is_a_404()
    {
        using var lab = new Lab();
        var bad = await lab.RequestsHttp.PostAsJsonAsync("/api/requests", new { title = "x", departmentCode = "FIN", amount = 0, requestedBy = "nope" });
        Assert.Equal(HttpStatusCode.BadRequest, bad.StatusCode);
        var problem = await bad.Content.ReadAsStringAsync();
        Assert.Contains("Title", problem); Assert.Contains("Amount", problem); Assert.Contains("RequestedBy", problem);

        var badKey = new HttpRequestMessage(HttpMethod.Post, "/api/requests")
        { Content = JsonContent.Create(Lab.NewRequest()), Headers = { { "Idempotency-Key", "nope" } } };
        Assert.Equal(HttpStatusCode.BadRequest, (await lab.RequestsHttp.SendAsync(badKey)).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await lab.RequestsHttp.GetAsync("/api/requests/999")).StatusCode);
        Assert.Equal(0, lab.BudgetWire.Attempts);                // nothing invalid ever reached the other service
    }

    [Fact]
    public async Task The_trace_id_of_the_request_is_stored_with_it()
    {
        using var lab = new Lab();
        var dto = (await (await lab.RequestsHttp.PostAsJsonAsync("/api/requests", Lab.NewRequest()))
            .Content.ReadFromJsonAsync<RequestDto>())!;
        Assert.Matches("^[0-9a-f]{32}$", dto.TraceId);
    }

    [Fact]
    public async Task Alive_and_health_answer()
    {
        using var lab = new Lab();
        Assert.Equal("Healthy", await lab.RequestsHttp.GetStringAsync("/alive"));
        Assert.Equal("Healthy", await lab.RequestsHttp.GetStringAsync("/health"));
        Assert.Equal("Healthy", await lab.BudgetHttp.GetStringAsync("/alive"));
    }
}
