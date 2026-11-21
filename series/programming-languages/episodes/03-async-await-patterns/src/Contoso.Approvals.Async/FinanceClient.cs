using System.Net.Http.Json;

namespace Contoso.Approvals;

public interface IFinanceClient
{
    Task<BudgetInfo> GetBudgetAsync(string costCenter, CancellationToken ct);
    Task<Approver> GetApproverAsync(string department, CancellationToken ct);
    IAsyncEnumerable<ProjectRequest> StreamRequestsAsync(CancellationToken ct);
}

/// <summary>
/// Typed HttpClient for the Contoso Finance API. Every method takes the caller's CancellationToken and hands it to
/// HttpClient, so cancelling really aborts the HTTP request (the API sees it as RequestAborted).
/// Library code: ConfigureAwait(false) on every await, because it never needs the caller's context.
/// </summary>
public sealed class FinanceClient(HttpClient http) : IFinanceClient
{
    public Task<BudgetInfo> GetBudgetAsync(string costCenter, CancellationToken ct) =>
        GetAsync<BudgetInfo>($"budget/{Uri.EscapeDataString(costCenter)}", ct);

    public Task<Approver> GetApproverAsync(string department, CancellationToken ct) =>
        GetAsync<Approver>($"approver/{Uri.EscapeDataString(department)}", ct);

    /// <summary>Items arrive while the response is still streaming. .NET 10 ships LINQ for IAsyncEnumerable (OfType).</summary>
    public IAsyncEnumerable<ProjectRequest> StreamRequestsAsync(CancellationToken ct) =>
        http.GetFromJsonAsAsyncEnumerable<ProjectRequest>("requests", ct).OfType<ProjectRequest>();

    private async Task<T> GetAsync<T>(string path, CancellationToken ct)
    {
        var value = await http.GetFromJsonAsync<T>(path, ct).ConfigureAwait(false);
        return value ?? throw new InvalidOperationException($"Empty response from {path}.");
    }
}
