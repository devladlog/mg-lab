using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using ProjectRequests.Contracts;

namespace ProjectRequests.Web.Client.Services;

/// <summary>The project requests API, as the UI sees it. Used by server components and by WebAssembly components.</summary>
public interface IRequestsApi
{
    Task<IReadOnlyList<RequestDto>> ListAsync(CancellationToken ct = default);
    Task<RequestDto?> GetAsync(int id, CancellationToken ct = default);
    Task<ApiResult<RequestDto>> CreateAsync(CreateProjectRequest input, CancellationToken ct = default);
    Task<ApiResult<RequestDto>> DecideAsync(int id, DecisionRequest decision, CancellationToken ct = default);
}

/// <summary>Either a value, or what the API said was wrong (problem details title/detail and field errors).</summary>
public sealed record ApiResult<T>(T? Value, string? Problem, IReadOnlyDictionary<string, string[]> Errors)
    where T : class
{
    public bool Succeeded => Value is not null;

    public static ApiResult<T> Ok(T value) => new(value, null, new Dictionary<string, string[]>());
}

/// <summary>
/// Plain HttpClient: in the browser it's the one registered in the client's Program.cs (fetch under the hood);
/// on the server it's a typed client from IHttpClientFactory.
/// </summary>
public sealed class RequestsApiClient(HttpClient http) : IRequestsApi
{
    /// <summary>The API writes enums as strings (JsonStringEnumConverter); read them the same way.</summary>
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
    {
        Converters = { new JsonStringEnumConverter() },
    };

    public async Task<IReadOnlyList<RequestDto>> ListAsync(CancellationToken ct = default) =>
        await http.GetFromJsonAsync<List<RequestDto>>("api/requests", Json, ct) ?? [];

    public async Task<RequestDto?> GetAsync(int id, CancellationToken ct = default)
    {
        using var response = await http.GetAsync($"api/requests/{id}", ct);
        if (response.StatusCode == HttpStatusCode.NotFound)
            return null;
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<RequestDto>(Json, ct);
    }

    public async Task<ApiResult<RequestDto>> CreateAsync(CreateProjectRequest input, CancellationToken ct = default) =>
        await ReadAsync(await http.PostAsJsonAsync("api/requests", input, Json, ct), ct);

    public async Task<ApiResult<RequestDto>> DecideAsync(int id, DecisionRequest decision, CancellationToken ct = default) =>
        await ReadAsync(await http.PostAsJsonAsync($"api/requests/{id}/decision", decision, Json, ct), ct);

    private static async Task<ApiResult<RequestDto>> ReadAsync(HttpResponseMessage response, CancellationToken ct)
    {
        using (response)
        {
            if (response.IsSuccessStatusCode)
                return ApiResult<RequestDto>.Ok((await response.Content.ReadFromJsonAsync<RequestDto>(Json, ct))!);

            // 400 validation problem or 409 problem: application/problem+json
            var problem = await response.Content.ReadFromJsonAsync<Problem>(Json, ct);
            var message = problem?.Detail is { Length: > 0 } detail ? $"{problem.Title} {detail}" : problem?.Title;
            return new ApiResult<RequestDto>(null, message ?? $"The API returned {(int)response.StatusCode}.",
                problem?.Errors ?? new Dictionary<string, string[]>());
        }
    }

    private sealed record Problem(string? Title, string? Detail, Dictionary<string, string[]>? Errors);
}
