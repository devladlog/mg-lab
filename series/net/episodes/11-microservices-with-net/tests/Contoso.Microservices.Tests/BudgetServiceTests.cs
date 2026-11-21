using System.Net;
using System.Net.Http.Json;
using Contoso.Budget.Service;

namespace Contoso.Microservices.Tests;

public class BudgetServiceTests : IDisposable
{
    private readonly Lab _lab = new();
    public void Dispose() => _lab.Dispose();

    private static HttpRequestMessage Reserve(string department, decimal amount, Guid? key = null, string reference = "r1")
    {
        var request = new HttpRequestMessage(HttpMethod.Post, $"/api/budgets/{department}/reservations")
        { Content = JsonContent.Create(new { amount, reference }) };
        if (key is { } k) request.Headers.Add("Idempotency-Key", k.ToString());
        return request;
    }

    private async Task<BudgetStatus> Status(HttpClient http, string department) =>
        (await http.GetFromJsonAsync<BudgetStatus>($"/api/budgets/{department}"))!;

    [Fact]
    public async Task A_reservation_within_the_limit_is_created_and_reduces_what_is_left()
    {
        var response = await _lab.BudgetHttp.SendAsync(Reserve("FIN", 12_000m, Guid.NewGuid()));
        Assert.Equal(HttpStatusCode.Created, response.StatusCode);
        var status = await Status(_lab.BudgetHttp, "FIN");
        Assert.Equal(50_000m, status.Limit);
        Assert.Equal(12_000m, status.Reserved);
        Assert.Equal(38_000m, status.Remaining);
    }

    [Fact]
    public async Task Over_the_limit_is_422_and_changes_nothing()
    {
        var response = await _lab.BudgetHttp.SendAsync(Reserve("OPS", 20_000.01m, Guid.NewGuid()));
        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
        Assert.Equal(0m, (await Status(_lab.BudgetHttp, "OPS")).Reserved);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("not-a-guid")]
    public async Task A_reservation_without_a_valid_idempotency_key_is_refused(string? key)
    {
        var request = Reserve("FIN", 100m);
        if (key is not null) request.Headers.Add("Idempotency-Key", key);
        Assert.Equal(HttpStatusCode.BadRequest, (await _lab.BudgetHttp.SendAsync(request)).StatusCode);
    }

    [Fact]
    public async Task Repeating_the_same_call_returns_the_first_answer_and_reserves_once()
    {
        var key = Guid.NewGuid();
        var first = await _lab.BudgetHttp.SendAsync(Reserve("IT", 5_000m, key));
        var second = await _lab.BudgetHttp.SendAsync(Reserve("IT", 5_000m, key));
        Assert.Equal(HttpStatusCode.Created, first.StatusCode);
        Assert.Equal(HttpStatusCode.OK, second.StatusCode);
        Assert.Equal((await first.Content.ReadFromJsonAsync<Reservation>())!.Id, (await second.Content.ReadFromJsonAsync<Reservation>())!.Id);
        Assert.Equal(5_000m, (await Status(_lab.BudgetHttp, "IT")).Reserved);
    }

    [Fact]
    public async Task Reusing_a_key_for_a_different_reservation_is_a_conflict()
    {
        var key = Guid.NewGuid();
        await _lab.BudgetHttp.SendAsync(Reserve("IT", 5_000m, key));
        var other = await _lab.BudgetHttp.SendAsync(Reserve("IT", 6_000m, key));
        Assert.Equal(HttpStatusCode.Conflict, other.StatusCode);
        Assert.Equal(5_000m, (await Status(_lab.BudgetHttp, "IT")).Reserved);
    }

    [Fact]
    public async Task An_unknown_department_is_404_and_a_negative_amount_is_a_validation_error()
    {
        Assert.Equal(HttpStatusCode.NotFound, (await _lab.BudgetHttp.SendAsync(Reserve("XYZ", 10m, Guid.NewGuid()))).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await _lab.BudgetHttp.GetAsync("/api/budgets/XYZ")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await _lab.BudgetHttp.SendAsync(Reserve("FIN", -5m, Guid.NewGuid()))).StatusCode);
    }

    [Fact]
    public async Task Fifty_parallel_reservations_never_go_over_the_limit()
    {
        // OPS has 20,000: of fifty parallel calls of 1,000, exactly twenty may win.
        var results = await Task.WhenAll(Enumerable.Range(0, 50)
            .Select(_ => Task.Run(() => _lab.BudgetHttp.SendAsync(Reserve("OPS", 1_000m, Guid.NewGuid())))));
        Assert.Equal(20, results.Count(r => r.StatusCode == HttpStatusCode.Created));
        Assert.Equal(30, results.Count(r => r.StatusCode == HttpStatusCode.UnprocessableEntity));
        Assert.Equal(0m, (await Status(_lab.BudgetHttp, "OPS")).Remaining);
    }

    [Fact]
    public async Task A_lost_answer_does_not_reserve_twice_when_the_retry_carries_the_same_key()
    {
        using var lab = new Lab(failFirstAttempts: 2, failAfterCommit: true);
        var key = Guid.NewGuid();

        // Attempts 1 and 2: the reservation is made, the answer is lost (503).
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await lab.BudgetHttp.SendAsync(Reserve("FIN", 7_000m, key))).StatusCode);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, (await lab.BudgetHttp.SendAsync(Reserve("FIN", 7_000m, key))).StatusCode);
        // Attempt 3 gets the first reservation back.
        Assert.Equal(HttpStatusCode.OK, (await lab.BudgetHttp.SendAsync(Reserve("FIN", 7_000m, key))).StatusCode);
        Assert.Equal(7_000m, (await Status(lab.BudgetHttp, "FIN")).Reserved);   // not 21,000
    }
}
