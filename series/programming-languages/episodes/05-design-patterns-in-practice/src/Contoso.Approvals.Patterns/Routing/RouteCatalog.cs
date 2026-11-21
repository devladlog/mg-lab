using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns.Routing;

/// <summary>
/// Picks the strategy. It receives every registered <see cref="IApprovalRoute"/> through
/// <c>IEnumerable&lt;T&gt;</c>, so adding a route is one new class plus one registration line,
/// and nothing here asks the container for services at run time (no service locator).
/// </summary>
public sealed class RouteCatalog
{
    private readonly Dictionary<string, IApprovalRoute> _routes;
    private readonly IOptions<ApprovalPolicyOptions> _policy;

    public RouteCatalog(IEnumerable<IApprovalRoute> routes, IOptions<ApprovalPolicyOptions> policy)
    {
        _routes = [];
        foreach (var route in routes)
        {
            if (!_routes.TryAdd(route.Key, route))
            {
                throw new InvalidOperationException(
                    $"Two approval routes use the key '{route.Key}': {_routes[route.Key].GetType().Name} and {route.GetType().Name}.");
            }
        }

        _policy = policy;
    }

    public IReadOnlyCollection<string> Keys => [.. _routes.Keys.Order(StringComparer.Ordinal)];

    public IApprovalRoute For(ProjectRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        var key = RouteKeys.For(request.Budget, _policy.Value);
        return _routes.TryGetValue(key, out var route)
            ? route
            : throw new InvalidOperationException(
                $"No approval route registered for '{key}'. Registered: {string.Join(", ", Keys)}.");
    }
}
