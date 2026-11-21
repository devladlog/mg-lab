using System.Net.Http.Headers;
using Azure.Core;

namespace Contoso.Orders.Client;

/// <summary>
/// Adds "Authorization: Bearer ..." to every request, with a token for the API from any Azure.Identity credential
/// (a managed identity in Azure, the Azure CLI on a laptop). No secret anywhere in the client.
/// App permissions are requested with the "{App ID URI}/.default" scope: the token then carries every app role
/// assigned to the identity; individual role names can't be requested.
/// </summary>
public sealed class EntraTokenHandler : DelegatingHandler
{
    private readonly TokenCredential credential;
    private readonly string[] scopes;

    public EntraTokenHandler(TokenCredential credential, string scope)
    {
        if (!scope.EndsWith("/.default", StringComparison.Ordinal))
            throw new ArgumentException($"App-only calls need the '/.default' scope, got '{scope}'.", nameof(scope));
        this.credential = credential;
        scopes = [scope];
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        // Ask on every request: a credential that caches tokens hands back the cached one until it nears expiry.
        AccessToken token = await credential.GetTokenAsync(new TokenRequestContext(scopes), ct);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Token);
        return await base.SendAsync(request, ct);
    }
}
