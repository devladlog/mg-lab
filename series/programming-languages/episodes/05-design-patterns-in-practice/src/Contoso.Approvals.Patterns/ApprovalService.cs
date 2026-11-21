using Contoso.Approvals.Patterns.Approvers;
using Contoso.Approvals.Patterns.Events;
using Contoso.Approvals.Patterns.Routing;

namespace Contoso.Approvals.Patterns;

/// <summary>
/// The client of all three patterns. It only knows interfaces: a route catalog (strategy),
/// an approver directory (decorated), and a list of observers.
/// </summary>
public sealed class ApprovalService(
    RouteCatalog routes,
    IApproverDirectory directory,
    IEnumerable<IRequestObserver> observers)
{
    private readonly IRequestObserver[] _observers = [.. observers];

    public async Task<SubmitResult> SubmitAsync(ProjectRequest request, CancellationToken cancellationToken = default)
    {
        var plan = routes.For(request).Plan(request);

        List<ApprovalStep> steps = [];
        foreach (var role in plan.Roles)
        {
            var approver = await directory.FindAsync(request.Department, role, cancellationToken).ConfigureAwait(false);
            steps.Add(new ApprovalStep(role, approver));
        }

        var routed = new RequestRouted(request, plan.Route, steps, plan.DueInDays, plan.Warnings);
        return new SubmitResult(routed, await PublishAsync(routed, cancellationToken).ConfigureAwait(false));
    }

    /// <summary>Every observer runs, in registration order; one failing observer doesn't stop the others.</summary>
    private async Task<IReadOnlyList<string>> PublishAsync(RequestRouted routed, CancellationToken cancellationToken)
    {
        List<string> failures = [];
        foreach (var observer in _observers)
        {
            try
            {
                await observer.OnRoutedAsync(routed, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                failures.Add($"{observer.GetType().Name}: {ex.Message}");
            }
        }

        return failures;
    }
}
