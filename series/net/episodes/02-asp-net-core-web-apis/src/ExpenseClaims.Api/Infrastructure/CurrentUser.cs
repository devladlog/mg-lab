using System.Security.Claims;

namespace ExpenseClaims.Api.Infrastructure;

public static class CurrentUser
{
    public const string ApproverRole = "Claims.Approve";

    /// <summary>
    /// Stable user id. Microsoft Entra access tokens carry "oid" (object id); dotnet user-jwts tokens carry "sub".
    /// Inbound claim mapping is off (MapInboundClaims = false), so we read the raw JWT claim names.
    /// </summary>
    public static string Id(ClaimsPrincipal user) =>
        user.FindFirstValue("oid") ?? user.FindFirstValue("sub")
        ?? throw new InvalidOperationException("The token has no oid or sub claim.");
}
