using System.Net;
using System.Text;
using Contoso.Mobile.Core.Api;
using Contoso.Mobile.Core.Models;

namespace Contoso.Mobile.Tests;

public class ApiEndpointsTests
{
    [Fact] public void Android_emulator_reaches_the_dev_machine_at_10_0_2_2() =>
        Assert.Equal("http://10.0.2.2:5311/", ApiEndpoints.BaseAddress("Android").ToString());

    [Theory]
    [InlineData("Other")] [InlineData("iOS")] [InlineData("WinUI")]
    public void Other_platforms_use_localhost(string platform) =>
        Assert.Equal("http://localhost:5311/", ApiEndpoints.BaseAddress(platform).ToString());

    [Fact] public void A_physical_device_uses_the_address_it_was_given() =>
        Assert.Equal("http://192.168.1.50:5311/", ApiEndpoints.BaseAddress("Android", " http://192.168.1.50:5311 ").ToString());

    [Fact] public void A_bad_override_is_refused() =>
        Assert.Throws<ArgumentException>(() => ApiEndpoints.BaseAddress("Android", "ftp://nope"));
}

public class RequestsApiTests
{
    private static (RequestsApi Api, StubHandler Handler) Build(Func<HttpRequestMessage, Task<HttpResponseMessage>> respond)
    {
        var handler = new StubHandler(respond);
        return (new RequestsApi(new HttpClient(handler) { BaseAddress = new Uri("http://localhost:5311") }), handler);
    }

    private static HttpResponseMessage Json(HttpStatusCode code, string json) =>
        new(code) { Content = new StringContent(json, Encoding.UTF8, "application/json") };

    private const string ItemJson = """{"id":7,"title":"Standing desks","department":"FIN","amount":12000.0,"requestedBy":"alex.demo@contoso.com","budgetState":"Reserved","idempotencyKey":"00000000-0000-0000-0000-000000000001","traceId":"abc","createdAtUtc":"2026-11-21T10:00:00Z"}""";
    private static readonly DraftRequest Draft = new(Guid.Parse("00000000-0000-0000-0000-000000000001"), "Standing desks", "FIN", 12_000m, "alex.demo@contoso.com", DateTime.UtcNow);

    [Fact]
    public async Task The_list_is_read_from_the_gateway_and_unknown_fields_are_ignored()
    {
        var (api, handler) = Build(_ => Task.FromResult(Json(HttpStatusCode.OK, $"[{ItemJson}]")));
        var items = await api.ListAsync();
        var item = Assert.Single(items);
        Assert.Equal(("Standing desks", "FIN", 12_000m, "Reserved"), (item.Title, item.Department, item.Amount, item.BudgetState));
        Assert.Equal("/api/requests", handler.Calls.Single().Path);
    }

    [Fact]
    public async Task A_submit_sends_the_drafts_key_as_Idempotency_Key_and_the_body_the_server_expects()
    {
        var (api, handler) = Build(_ => Task.FromResult(Json(HttpStatusCode.Created, ItemJson)));
        var result = await api.SubmitAsync(Draft);
        Assert.Equal(SubmitOutcome.Created, result.Outcome);
        Assert.Equal(7, result.Item!.Id);
        var call = handler.Calls.Single();
        Assert.Equal((HttpMethod.Post, "/api/requests", Draft.Key.ToString()), (call.Method, call.Path, call.Key));
        Assert.Contains("\"departmentCode\":\"FIN\"", call.Body);
        Assert.Contains("\"requestedBy\":\"alex.demo@contoso.com\"", call.Body);
    }

    [Theory]
    [InlineData(HttpStatusCode.Created, SubmitOutcome.Created)]
    [InlineData(HttpStatusCode.OK, SubmitOutcome.Replayed)]
    [InlineData(HttpStatusCode.Accepted, SubmitOutcome.Accepted)]
    public async Task Success_codes_map_to_outcomes_and_count_as_stored(HttpStatusCode code, SubmitOutcome expected)
    {
        var (api, _) = Build(_ => Task.FromResult(Json(code, ItemJson)));
        var result = await api.SubmitAsync(Draft);
        Assert.Equal(expected, result.Outcome);
        Assert.True(result.IsStored);
    }

    [Fact]
    public async Task A_validation_problem_from_ASP_NET_Core_becomes_a_readable_rejection()
    {
        var (api, _) = Build(_ => Task.FromResult(Json(HttpStatusCode.BadRequest,
            """{"title":"One or more validation errors occurred.","status":400,"errors":{"Title":["The field Title must be a string with a minimum length of 3."],"Amount":["The field Amount must be between 1 and 10000000."]}}""")));
        var result = await api.SubmitAsync(Draft);
        Assert.Equal(SubmitOutcome.Rejected, result.Outcome);
        Assert.Contains("Title: The field Title must be", result.Error);
        Assert.Contains("Amount: The field Amount", result.Error);
    }

    [Fact]
    public async Task A_conflict_is_rejected_with_the_problem_title()
    {
        var (api, _) = Build(_ => Task.FromResult(Json(HttpStatusCode.Conflict, """{"title":"Idempotency-Key already used.","status":409}""")));
        var result = await api.SubmitAsync(Draft);
        Assert.Equal((SubmitOutcome.Rejected, "Idempotency-Key already used."), (result.Outcome, result.Error));
    }

    [Theory]
    [InlineData(HttpStatusCode.ServiceUnavailable)]
    [InlineData(HttpStatusCode.BadGateway)]
    [InlineData(HttpStatusCode.InternalServerError)]
    [InlineData(HttpStatusCode.RequestTimeout)]
    [InlineData(HttpStatusCode.TooManyRequests)]
    public async Task Server_trouble_means_try_again_later_not_rejected(HttpStatusCode code)
    {
        var (api, _) = Build(_ => Task.FromResult(new HttpResponseMessage(code)));
        Assert.Equal(SubmitOutcome.Unavailable, (await api.SubmitAsync(Draft)).Outcome);
    }

    [Fact]
    public async Task No_network_and_timeouts_are_unavailable_and_the_list_throws_for_the_caller_to_handle()
    {
        var (down, _) = Build(_ => throw new HttpRequestException("no route to host"));
        Assert.Equal(SubmitOutcome.Unavailable, (await down.SubmitAsync(Draft)).Outcome);
        await Assert.ThrowsAsync<ApiUnavailableException>(() => down.ListAsync());

        var (slow, _) = Build(_ => throw new TaskCanceledException("HttpClient.Timeout"));
        Assert.Equal(SubmitOutcome.Unavailable, (await slow.SubmitAsync(Draft)).Outcome);
    }

    [Fact]
    public async Task The_callers_own_cancellation_is_not_swallowed()
    {
        var (api, _) = Build(_ => throw new TaskCanceledException("cancelled"));
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();
        await Assert.ThrowsAsync<TaskCanceledException>(() => api.SubmitAsync(Draft, cts.Token));
    }
}
