using Contoso.Mobile.Core.Api;
using Contoso.Mobile.Core.Models;
using Contoso.Mobile.Core.Offline;
using Contoso.Mobile.Core.ViewModels;

namespace Contoso.Mobile.Tests;

public sealed class FakeConnectivity : IConnectivityService
{
    public bool IsOnline { get; set; } = true;
    public event EventHandler? Changed;
    public void Switch(bool online) { IsOnline = online; Changed?.Invoke(this, EventArgs.Empty); }
}

public sealed class InlineUi : IUiThread { public void Post(Action action) => action(); }

/// <summary>A scripted server: records every draft it is asked to submit, answers from a queue (then "Created").</summary>
public sealed class FakeApi : IRequestsApi
{
    private readonly object _gate = new();
    public List<DraftRequest> Submitted { get; } = [];
    public Queue<SubmitResult> Script { get; } = new();
    public List<RequestItem> Server { get; } = [];
    public bool ListFails { get; set; }
    public TimeSpan Delay { get; set; }

    public async Task<SubmitResult> SubmitAsync(DraftRequest draft, CancellationToken ct = default)
    {
        lock (_gate) Submitted.Add(draft);
        if (Delay > TimeSpan.Zero) await Task.Delay(Delay, ct);
        lock (_gate)
        {
            var result = Script.Count > 0 ? Script.Dequeue() : new SubmitResult(SubmitOutcome.Created);
            if (result.IsStored)
                Server.Add(new RequestItem(Server.Count + 1, draft.Title, draft.DepartmentCode, draft.Amount, draft.RequestedBy, "Reserved", draft.QueuedAtUtc));
            return result;
        }
    }

    public Task<IReadOnlyList<RequestItem>> ListAsync(CancellationToken ct = default) =>
        ListFails ? throw new ApiUnavailableException("down") : Task.FromResult<IReadOnlyList<RequestItem>>(Server.ToList());
}

/// <summary>Everything on disk lives in a temp folder that goes away with the test.</summary>
public sealed class TempDir : IDisposable
{
    public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "mobile-tests-" + Guid.NewGuid().ToString("N"));
    public TempDir() => Directory.CreateDirectory(Path);
    public string File(string name) => System.IO.Path.Combine(Path, name);
    public void Dispose() { try { Directory.Delete(Path, true); } catch (IOException) { } }
}

public sealed class StubHandler(Func<HttpRequestMessage, Task<HttpResponseMessage>> respond) : HttpMessageHandler
{
    public List<(HttpMethod Method, string Path, string? Key, string Body)> Calls { get; } = [];

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        var body = request.Content is null ? "" : await request.Content.ReadAsStringAsync(ct);
        Calls.Add((request.Method, request.RequestUri!.PathAndQuery,
            request.Headers.TryGetValues("Idempotency-Key", out var v) ? v.Single() : null, body));
        return await respond(request);
    }
}
