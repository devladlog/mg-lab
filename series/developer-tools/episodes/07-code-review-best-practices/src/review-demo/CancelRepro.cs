using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Orders.Api;

namespace Contoso.Orders.Api.Tests;

/// <summary>The reviewer's reproduction of the two review comments, written against the code as submitted.</summary>
public class CancelRepro(ApiFactory factory) : IClassFixture<ApiFactory>
{
    private readonly HttpClient _client = factory.CreateClient();

    [Fact]
    public async Task Cancelling_an_unknown_order_is_404_not_500()
    {
        var response = await _client.PostAsync("/orders/2147483647/cancel", content: null);
        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task Cancelling_twice_is_a_409_with_a_reason()
    {
        var created = await (await _client.PostAsJsonAsync("/orders", new NewOrder("Alex Demo", 10m)))
            .Content.ReadFromJsonAsync<Order>();
        Assert.Equal(HttpStatusCode.OK, (await _client.PostAsync($"/orders/{created!.Id}/cancel", content: null)).StatusCode);

        var again = await _client.PostAsync($"/orders/{created.Id}/cancel", content: null);

        Assert.Equal(HttpStatusCode.Conflict, again.StatusCode);
        var problem = await again.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("The order is already cancelled", problem.GetProperty("title").GetString());
    }
}
