using Contoso.Approvals.Patterns.Events;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns.Tests;

public class ObserverTests
{
    [Fact]
    public async Task Observers_run_in_registration_order()
    {
        var calls = new List<string>();
        using var sp = TestHost.Provider(extra: s =>
        {
            s.AddSingleton<IRequestObserver>(new Recording("first", calls));
            s.AddSingleton<IRequestObserver>(new Recording("second", calls));
        });
        using var scope = sp.CreateScope();

        await scope.ServiceProvider.GetRequiredService<ApprovalService>().SubmitAsync(TestHost.Request(1_000m));

        Assert.Equal(["first", "second"], calls);
        Assert.Equal(
            ["AuditObserver", "OutboxObserver", "BudgetTallyObserver", "Recording", "Recording"],
            scope.ServiceProvider.GetServices<IRequestObserver>().Select(o => o.GetType().Name));
    }

    [Fact]
    public async Task A_failing_observer_does_not_stop_the_others()
    {
        var calls = new List<string>();
        using var sp = TestHost.Provider(extra: s =>
        {
            s.AddSingleton<IRequestObserver, Failing>();
            s.AddSingleton<IRequestObserver>(new Recording("after the failure", calls));
        });
        using var scope = sp.CreateScope();

        var result = await scope.ServiceProvider.GetRequiredService<ApprovalService>().SubmitAsync(TestHost.Request(1_000m));

        Assert.Equal(["Failing: mail server unavailable"], result.ObserverFailures);
        Assert.Equal(["after the failure"], calls);
        Assert.Single(scope.ServiceProvider.GetRequiredService<AuditTrail>().Entries);
    }

    [Fact]
    public async Task Each_scope_gets_its_own_audit_trail()
    {
        using var sp = TestHost.Provider();

        foreach (var budget in new[] { 1_000m, 60_000m })
        {
            using var scope = sp.CreateScope();
            await scope.ServiceProvider.GetRequiredService<ApprovalService>().SubmitAsync(TestHost.Request(budget));
            Assert.Single(scope.ServiceProvider.GetRequiredService<AuditTrail>().Entries);
        }

        Assert.Equal(2, sp.GetRequiredService<BudgetTally>().Snapshot().Sum(t => t.Count)); // singleton sees both
    }

    [Fact]
    public async Task The_outbox_observer_writes_one_file_for_the_first_approver()
    {
        var folder = Path.Combine(Path.GetTempPath(), "mglab-ep05-" + Guid.NewGuid().ToString("N"));
        try
        {
            using var sp = TestHost.Provider(TestHost.Config(("Outbox:Folder", folder)));
            using var scope = sp.CreateScope();

            await scope.ServiceProvider.GetRequiredService<ApprovalService>().SubmitAsync(TestHost.Request(300_000m, justification: "Needed"));

            var text = await File.ReadAllTextAsync(Path.Combine(folder, "PR-2026-0999.txt"));
            Assert.StartsWith("To: Sam Demo (Finance)\n", text, StringComparison.Ordinal);
            Assert.Contains("route board, due in 20 days", text, StringComparison.Ordinal);
        }
        finally
        {
            if (Directory.Exists(folder))
            {
                Directory.Delete(folder, recursive: true);
            }
        }
    }

    [Fact]
    public void Gotcha_resolving_one_observer_silently_gives_you_the_last_registration()
    {
        using var sp = TestHost.Provider();
        using var scope = sp.CreateScope();

        Assert.IsType<BudgetTallyObserver>(scope.ServiceProvider.GetRequiredService<IRequestObserver>());
    }

    private sealed class Recording(string name, List<string> calls) : IRequestObserver
    {
        public Task OnRoutedAsync(RequestRouted routed, CancellationToken cancellationToken)
        {
            calls.Add(name);
            return Task.CompletedTask;
        }
    }

    private sealed class Failing : IRequestObserver
    {
        public Task OnRoutedAsync(RequestRouted routed, CancellationToken cancellationToken) =>
            throw new IOException("mail server unavailable");
    }
}
