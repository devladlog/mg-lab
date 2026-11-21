using System.Net;
using Polly.CircuitBreaker;
using Polly.Timeout;

namespace Contoso.Requests.Service.Budget;

public enum BudgetAnswer { Reserved, Declined, Unavailable }

public sealed record BudgetResult(BudgetAnswer Answer, Guid? ReservationId = null, string? Detail = null);

public sealed record ReservationDto(Guid Id, string Department, decimal Amount, string Reference);

/// <summary>
/// The only place that knows the Budget service exists. The HttpClient under it has service discovery
/// ("http://budget") and the standard resilience handler (retry, circuit breaker, timeouts) from ServiceDefaults.
/// </summary>
public sealed class BudgetClient(HttpClient http, ILogger<BudgetClient> log)
{
    public async Task<BudgetResult> ReserveAsync(string department, decimal amount, string reference, Guid key, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, $"/api/budgets/{Uri.EscapeDataString(department)}/reservations")
        {
            Content = JsonContent.Create(new { amount, reference }),
        };
        request.Headers.Add(Contoso.ServiceDefaults.Idempotency.Header, key.ToString());   // makes the retries safe

        try
        {
            using var response = await http.SendAsync(request, ct);
            if (response.IsSuccessStatusCode)
            {
                var reservation = await response.Content.ReadFromJsonAsync<ReservationDto>(ct);
                return new BudgetResult(BudgetAnswer.Reserved, reservation?.Id);
            }
            if (response.StatusCode == HttpStatusCode.UnprocessableEntity)   // a real answer: no
                return new BudgetResult(BudgetAnswer.Declined, Detail: "Over budget");

            // 5xx after the retries are used up, or something we did wrong (4xx): not "no", just "not now".
            log.LogWarning("Budget service answered {Status}; the request stays pending", (int)response.StatusCode);
            return new BudgetResult(BudgetAnswer.Unavailable, Detail: $"HTTP {(int)response.StatusCode}");
        }
        catch (BrokenCircuitException)
        {
            log.LogWarning("Circuit to the Budget service is open: failing fast, the request stays pending");
            return new BudgetResult(BudgetAnswer.Unavailable, Detail: "circuit open");
        }
        catch (Exception e) when (e is HttpRequestException or TimeoutRejectedException or TaskCanceledException && !ct.IsCancellationRequested)
        {
            log.LogWarning("Budget service not reachable ({Error}); the request stays pending", e.GetType().Name);
            return new BudgetResult(BudgetAnswer.Unavailable, Detail: e.GetType().Name);
        }
    }
}
