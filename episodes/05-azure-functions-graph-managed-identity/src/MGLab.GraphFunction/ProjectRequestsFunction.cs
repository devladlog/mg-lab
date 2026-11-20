using System.IdentityModel.Tokens.Jwt;
using Azure.Core;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Graph;
using Microsoft.Graph.Models.ODataErrors;

namespace MGLab.GraphFunction;

public sealed class ProjectRequestsFunction(
    GraphServiceClient graph, TokenCredential credential, IConfiguration config, ILogger<ProjectRequestsFunction> log)
{
    private string SiteId => config["SHAREPOINT_SITE_ID"] ?? throw new InvalidOperationException("SHAREPOINT_SITE_ID is not set.");
    private string ListName => config["SHAREPOINT_LIST"] ?? "Project Requests";

    /// <summary>GET /api/requests?status=Approved — project requests from the SharePoint list, via Microsoft Graph.</summary>
    [Function("requests")]
    public async Task<IActionResult> GetRequests(
        [HttpTrigger(AuthorizationLevel.Function, "get", Route = "requests")] HttpRequest req)
    {
        string? status = req.Query["status"];
        try
        {
            var page = await graph.Sites[SiteId].Lists[ListName].Items.GetAsync(r =>
            {
                r.QueryParameters.Expand = ["fields($select=Title,Requester,Department,Budget,RequestStatus,DueDate)"];
                r.QueryParameters.Top = 200;
            });

            var items = (page?.Value ?? [])
                .Select(i => ProjectRequest.FromFields(i.Fields?.AdditionalData ?? new Dictionary<string, object?>()!))
                .Where(r => string.IsNullOrEmpty(status) || string.Equals(r.Status, status, StringComparison.OrdinalIgnoreCase))
                .OrderBy(r => r.DueDate)
                .ToList();

            log.LogInformation("Returned {Count} requests (status filter: {Status})", items.Count, status ?? "none");
            return new OkObjectResult(new { count = items.Count, status, items });
        }
        catch (ODataError e) when (e.ResponseStatusCode is 401 or 403)
        {
            // Least privilege in action: the identity only has access to the sites it was granted.
            log.LogWarning("Graph denied access: {Code} {Message}", e.Error?.Code, e.Error?.Message);
            return new ObjectResult(new { error = e.Error?.Code, message = e.Error?.Message }) { StatusCode = 403 };
        }
    }

    /// <summary>GET /api/whoami — which identity is calling Graph, and with which application roles. Never returns the token.</summary>
    [Function("whoami")]
    public async Task<IActionResult> WhoAmI(
        [HttpTrigger(AuthorizationLevel.Function, "get", Route = "whoami")] HttpRequest req, CancellationToken ct)
    {
        var token = await credential.GetTokenAsync(new TokenRequestContext(["https://graph.microsoft.com/.default"]), ct);
        var jwt = new JwtSecurityTokenHandler().ReadJwtToken(token.Token);
        string? Claim(string type) => jwt.Claims.FirstOrDefault(c => c.Type == type)?.Value;

        return new OkObjectResult(new
        {
            identityType = Claim("idtyp"),               // "app" for a managed identity
            appId = Claim("appid"),
            objectId = Claim("oid"),
            roles = jwt.Claims.Where(c => c.Type == "roles").Select(c => c.Value).ToArray(),
            expiresOn = token.ExpiresOn
        });
    }
}
