using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Contoso.Mobile.Core.Models;

namespace Contoso.Mobile.Core.Api;

public interface IRequestsApi
{
    Task<IReadOnlyList<RequestItem>> ListAsync(CancellationToken ct = default);
    Task<SubmitResult> SubmitAsync(DraftRequest draft, CancellationToken ct = default);
}

/// <summary>Thrown by <see cref="IRequestsApi.ListAsync"/> when the server can't be reached: the caller shows the saved list instead.</summary>
public sealed class ApiUnavailableException(string message, Exception? inner = null) : Exception(message, inner);

/// <summary>Talks to the gateway from episode 11 (<c>/api/requests</c>).</summary>
public sealed class RequestsApi(HttpClient http) : IRequestsApi
{
    public const string IdempotencyKeyHeader = "Idempotency-Key";

    public async Task<IReadOnlyList<RequestItem>> ListAsync(CancellationToken ct = default)
    {
        try
        {
            return await http.GetFromJsonAsync<List<RequestItem>>("/api/requests", JsonSerializerOptions.Web, ct) ?? [];
        }
        catch (Exception e) when (IsNetworkFailure(e, ct))
        {
            throw new ApiUnavailableException("The server can't be reached.", e);
        }
    }

    public async Task<SubmitResult> SubmitAsync(DraftRequest draft, CancellationToken ct = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/api/requests")
        {
            Content = JsonContent.Create(new { draft.Title, draft.DepartmentCode, draft.Amount, draft.RequestedBy }, options: JsonSerializerOptions.Web),
        };
        request.Headers.Add(IdempotencyKeyHeader, draft.Key.ToString());

        try
        {
            using var response = await http.SendAsync(request, ct);
            var item = response.IsSuccessStatusCode
                ? await response.Content.ReadFromJsonAsync<RequestItem>(JsonSerializerOptions.Web, ct) : null;
            return response.StatusCode switch
            {
                HttpStatusCode.Created => new SubmitResult(SubmitOutcome.Created, item),
                HttpStatusCode.OK => new SubmitResult(SubmitOutcome.Replayed, item),
                HttpStatusCode.Accepted => new SubmitResult(SubmitOutcome.Accepted, item),
                >= HttpStatusCode.InternalServerError or HttpStatusCode.RequestTimeout or HttpStatusCode.TooManyRequests
                    => new SubmitResult(SubmitOutcome.Unavailable, Error: $"HTTP {(int)response.StatusCode}"),
                _ => new SubmitResult(SubmitOutcome.Rejected, Error: await ReadProblemAsync(response, ct)),
            };
        }
        catch (Exception e) when (IsNetworkFailure(e, ct))
        {
            return new SubmitResult(SubmitOutcome.Unavailable, Error: e.GetType().Name);
        }
    }

    private static bool IsNetworkFailure(Exception e, CancellationToken ct) =>
        e is HttpRequestException or TaskCanceledException && !ct.IsCancellationRequested;

    /// <summary>ProblemDetails / ValidationProblemDetails from ASP.NET Core: field errors first, else the title.</summary>
    private static async Task<string> ReadProblemAsync(HttpResponseMessage response, CancellationToken ct)
    {
        try
        {
            using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync(ct));
            if (doc.RootElement.TryGetProperty("errors", out var errors) && errors.ValueKind == JsonValueKind.Object)
            {
                var messages = errors.EnumerateObject().SelectMany(p => p.Value.EnumerateArray().Select(m => $"{p.Name}: {m.GetString()}"));
                return string.Join(" ", messages);
            }
            if (doc.RootElement.TryGetProperty("title", out var title) && title.GetString() is { Length: > 0 } t) return t;
        }
        catch (JsonException) { }
        return $"HTTP {(int)response.StatusCode}";
    }
}
