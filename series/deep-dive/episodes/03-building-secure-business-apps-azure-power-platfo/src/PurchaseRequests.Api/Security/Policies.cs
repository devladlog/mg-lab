using System.Security.Claims;
using Microsoft.AspNetCore.Authorization;

namespace PurchaseRequests.Api.Security;

/// <summary>App role values defined on the API app registration (they arrive in the "roles" claim).</summary>
public static class AppRoles
{
    public const string Requester = "Requester";
    public const string Approver = "Approver";
    public const string FinanceApprover = "Finance.Approver";
}

public static class Policies
{
    public const string Read = "Read";
    public const string Submit = "Submit";
    public const string Decide = "Decide";

    /// <summary>
    /// Every policy requires a delegated user token: the scope in "scp" (so app-only tokens, which carry
    /// no "scp", are refused) and an object ID. Roles come on top of that.
    /// </summary>
    public static void AddPurchaseRequestPolicies(this AuthorizationOptions options, string requiredScope)
    {
        AuthorizationPolicyBuilder UserWithScope() => new AuthorizationPolicyBuilder()
            .RequireAuthenticatedUser()
            .RequireClaim("oid")
            .RequireAssertion(ctx => HasScope(ctx.User, requiredScope));

        options.AddPolicy(Read, UserWithScope().Build());
        options.AddPolicy(Submit, UserWithScope().RequireRole(AppRoles.Requester).Build());
        options.AddPolicy(Decide, UserWithScope().RequireRole(AppRoles.Approver, AppRoles.FinanceApprover).Build());
        // Nothing is allowed unless an endpoint says so explicitly.
        options.FallbackPolicy = UserWithScope().Build();
    }

    /// <summary>"scp" is one space-separated string in Entra access tokens.</summary>
    public static bool HasScope(ClaimsPrincipal user, string scope) =>
        user.FindAll("scp")
            .SelectMany(c => c.Value.Split(' ', StringSplitOptions.RemoveEmptyEntries))
            .Contains(scope, StringComparer.Ordinal);
}

/// <summary>Who is calling, taken only from the validated token, never from the request body.</summary>
public sealed record Caller(string Oid, string Name, bool IsApprover, bool IsFinanceApprover)
{
    public static Caller From(ClaimsPrincipal user)
    {
        var oid = user.FindFirstValue("oid")
            ?? throw new InvalidOperationException("Authorization policy should have required an oid claim.");
        return new Caller(
            oid,
            user.FindFirstValue("name") ?? "(unknown)",
            user.IsInRole(AppRoles.Approver) || user.IsInRole(AppRoles.FinanceApprover),
            user.IsInRole(AppRoles.FinanceApprover));
    }
}
