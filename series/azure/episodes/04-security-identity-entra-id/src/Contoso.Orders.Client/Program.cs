// The order processor: posts one order to the API as itself (app-only), using a managed identity in Azure.
//   ORDERS_API_URL     https://<api host>
//   ORDERS_API_SCOPE   api://<tenant id>/contoso-orders/.default
//   AZURE_CLIENT_ID    client ID of the user-assigned managed identity (unset on a laptop: Azure CLI is used)
using System.Net.Http.Json;
using Azure.Core;
using Azure.Identity;

namespace Contoso.Orders.Client;

internal static class Processor
{
    private static string Require(string name) => Environment.GetEnvironmentVariable(name)
        ?? throw new InvalidOperationException($"Set {name}.");

    public static async Task<int> Main()
    {
        var clientId = Environment.GetEnvironmentVariable("AZURE_CLIENT_ID");
        TokenCredential credential = string.IsNullOrEmpty(clientId)
            ? new AzureCliCredential()                                                         // developer laptop
            : new ManagedIdentityCredential(ManagedIdentityId.FromUserAssignedClientId(clientId)); // in Azure

        using var http = new HttpClient(new EntraTokenHandler(credential, Require("ORDERS_API_SCOPE"))
        {
            InnerHandler = new HttpClientHandler(),
        })
        {
            BaseAddress = new Uri(Require("ORDERS_API_URL")),
        };

        var response = await http.PostAsJsonAsync("/orders", new { customer = "Alex Demo", sku = "ABC-123", quantity = 2 });
        Console.WriteLine($"POST /orders -> {(int)response.StatusCode} {response.StatusCode}");
        Console.WriteLine(await response.Content.ReadAsStringAsync());
        return response.IsSuccessStatusCode ? 0 : 1;
    }
}
