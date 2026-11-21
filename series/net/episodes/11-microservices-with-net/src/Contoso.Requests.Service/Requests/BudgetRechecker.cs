using Contoso.Requests.Service.Budget;
using Contoso.Requests.Service.Data;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Requests.Service.Requests;

/// <summary>Finishes requests that were saved as Pending because the Budget service was not reachable.</summary>
public sealed class BudgetRechecker(IServiceScopeFactory scopes, ILogger<BudgetRechecker> log)
{
    public static void Apply(ProjectRequest request, BudgetResult result)
    {
        switch (result.Answer)
        {
            case BudgetAnswer.Reserved: request.BudgetState = BudgetState.Reserved; request.ReservationId = result.ReservationId; break;
            case BudgetAnswer.Declined: request.BudgetState = BudgetState.Declined; break;
        }
    }

    /// <summary>One pass. Returns how many requests changed state.</summary>
    public async Task<int> RunOnceAsync(CancellationToken ct)
    {
        using var scope = scopes.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<RequestsDb>();
        var budget = scope.ServiceProvider.GetRequiredService<BudgetClient>();

        var pending = await db.Requests.Where(r => r.BudgetState == BudgetState.Pending).OrderBy(r => r.Id).ToListAsync(ct);
        var changed = 0;
        foreach (var request in pending)
        {
            // Same idempotency key as the first attempt: if that one did reach the Budget service, this returns its answer.
            var result = await budget.ReserveAsync(request.Department, request.Amount, $"request-{request.Id}", request.IdempotencyKey, ct);
            if (result.Answer == BudgetAnswer.Unavailable) break;   // still down: stop, try again next pass
            Apply(request, result);
            changed++;
            log.LogInformation("Re-check: request {Id} is now {State}", request.Id, request.BudgetState);
        }
        await db.SaveChangesAsync(ct);
        return changed;
    }
}

public sealed class BudgetRecheckService(BudgetRechecker rechecker, IConfiguration config, ILogger<BudgetRecheckService> log)
    : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var seconds = config.GetValue("Recheck:IntervalSeconds", 10);
        if (seconds <= 0) return;   // switched off (the tests call RunOnceAsync themselves)
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(seconds));
        while (await timer.WaitForNextTickAsync(stoppingToken))
        {
            try { await rechecker.RunOnceAsync(stoppingToken); }
            catch (Exception e) when (e is not OperationCanceledException) { log.LogError(e, "Budget re-check pass failed"); }
        }
    }
}
