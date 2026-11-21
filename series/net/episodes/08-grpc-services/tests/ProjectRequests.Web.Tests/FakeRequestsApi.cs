namespace ProjectRequests.Web.Tests;

/// <summary>In-memory stand-in for the API, for component tests. Records what the UI sent.</summary>
public sealed class FakeRequestsApi : IRequestsApi
{
    public List<RequestDto> Requests { get; } = [];
    public List<CreateProjectRequest> Created { get; } = [];
    public List<(int Id, DecisionRequest Decision)> Decisions { get; } = [];
    public int GetCalls { get; private set; }

    /// <summary>Set to make the next write fail the way the API does (problem details).</summary>
    public ApiResult<RequestDto>? NextFailure { get; set; }

    public static RequestDto Sample(int id = 1, decimal budget = 12_000m, RequestStatus status = RequestStatus.Submitted) =>
        new(id, "Laptop refresh", budget, "FIN", "alex.demo@contoso.com", null, PriorityRules.Classify(budget), status,
            new DateTime(2026, 11, 21, 9, 0, 0, DateTimeKind.Utc), null, null, Guid.Parse("00000000-0000-0000-0000-000000000001"));

    /// <summary>
    /// A completed Task never yields, so stream rendering has nothing to stream: the page renders in one go.
    /// A delay makes the fake behave like a real HTTP call.
    /// </summary>
    public TimeSpan ListDelay { get; set; }

    public async Task<IReadOnlyList<RequestDto>> ListAsync(CancellationToken ct = default)
    {
        if (ListDelay > TimeSpan.Zero)
            await Task.Delay(ListDelay, ct);
        return Requests;
    }

    public Task<RequestDto?> GetAsync(int id, CancellationToken ct = default)
    {
        GetCalls++;
        return Task.FromResult(Requests.SingleOrDefault(r => r.Id == id));
    }

    /// <summary>What HttpClient throws in the browser when fetch fails (CORS refusal, API down).</summary>
    public bool Unreachable { get; set; }

    public Task<ApiResult<RequestDto>> CreateAsync(CreateProjectRequest input, CancellationToken ct = default)
    {
        Created.Add(input);
        if (Unreachable)
            throw new HttpRequestException("TypeError: Failed to fetch");
        if (TakeFailure() is { } failure)
            return Task.FromResult(failure);
        var dto = Sample(Requests.Count + 7, input.Budget) with { Title = input.Title, Department = input.DepartmentCode };
        Requests.Add(dto);
        return Task.FromResult(ApiResult<RequestDto>.Ok(dto));
    }

    public Task<ApiResult<RequestDto>> DecideAsync(int id, DecisionRequest decision, CancellationToken ct = default)
    {
        Decisions.Add((id, decision));
        if (TakeFailure() is { } failure)
            return Task.FromResult(failure);
        var current = Requests.Single(r => r.Id == id);
        var decided = current with
        {
            Status = decision.Approve == true ? RequestStatus.Approved : RequestStatus.Rejected,
            DecidedBy = decision.DecidedBy, Version = Guid.NewGuid(),
        };
        Requests[Requests.IndexOf(current)] = decided;
        return Task.FromResult(ApiResult<RequestDto>.Ok(decided));
    }

    private ApiResult<RequestDto>? TakeFailure()
    {
        var failure = NextFailure;
        NextFailure = null;
        return failure;
    }
}
