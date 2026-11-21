using Microsoft.AspNetCore.Authorization;
using Microsoft.Identity.Web;

namespace Contoso.Orders.Api;

/// <summary>
/// Who may do what. Delegated (user) tokens carry scopes in "scp"; app-only tokens carry app roles in "roles".
/// A user token can carry "roles" too (user app roles), so writing also requires idtyp = app.
/// </summary>
public static class AuthPolicies
{
    public const string ReadOrders = "orders.read";
    public const string WriteOrders = "orders.write";

    public const string ReadScope = "Orders.Read";             // delegated, for people (via a client app)
    public const string WriteAppRole = "Orders.ReadWrite.All";  // application permission, for workloads

    public static AuthorizationBuilder AddOrdersPolicies(this AuthorizationBuilder auth) => auth
        .AddPolicy(ReadOrders, p => p
            .RequireAuthenticatedUser()
            .RequireScopeOrAppPermission([ReadScope], [WriteAppRole]))
        .AddPolicy(WriteOrders, p => p
            .RequireAuthenticatedUser()
            .RequireScopeOrAppPermission([], [WriteAppRole])
            .RequireClaim("idtyp", "app"));   // optional claim configured on the app registration
}
