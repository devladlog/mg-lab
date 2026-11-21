using Grpc.Core;
using Microsoft.Extensions.Logging.Abstractions;
using ProjectRequests.Api.Rpc;

namespace ProjectRequests.Api.Tests;

/// <summary>The interceptor on its own, with a hand-made ServerCallContext (it is an abstract class).</summary>
public sealed class CancellationStatusInterceptorTests
{
    private readonly CancellationStatusInterceptor _interceptor = new(NullLogger<CancellationStatusInterceptor>.Instance);

    private sealed class FakeCallContext(DateTime deadline, CancellationToken token) : ServerCallContext
    {
        protected override string MethodCore => "/projectrequests.v1.Requests/Fake";
        protected override string HostCore => "localhost";
        protected override string PeerCore => "test";
        protected override DateTime DeadlineCore => deadline;
        protected override Metadata RequestHeadersCore => [];
        protected override CancellationToken CancellationTokenCore => token;
        protected override Metadata ResponseTrailersCore => [];
        protected override Status StatusCore { get; set; }
        protected override WriteOptions? WriteOptionsCore { get; set; }
        protected override AuthContext AuthContextCore => new(null, new Dictionary<string, List<AuthProperty>>());
        protected override ContextPropagationToken CreatePropagationTokenCore(ContextPropagationOptions? options) => throw new NotSupportedException();
        protected override Task WriteResponseHeadersAsyncCore(Metadata responseHeaders) => Task.CompletedTask;
    }

    private Task<string> Run(ServerCallContext context, Func<Task<string>> handler) =>
        _interceptor.UnaryServerHandler<string, string>("request", context, (_, _) => handler());

    [Fact]
    public async Task A_passed_deadline_becomes_DeadlineExceeded()
    {
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();
        var context = new FakeCallContext(DateTime.UtcNow.AddSeconds(-1), cts.Token);

        var ex = await Assert.ThrowsAsync<RpcException>(() => Run(context, () => throw new OperationCanceledException(cts.Token)));

        Assert.Equal(StatusCode.DeadlineExceeded, ex.StatusCode);
    }

    [Fact]
    public async Task A_client_that_went_away_becomes_Cancelled()
    {
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();
        var context = new FakeCallContext(DateTime.MaxValue, cts.Token);          // no deadline

        var ex = await Assert.ThrowsAsync<RpcException>(() => Run(context, () => throw new TaskCanceledException()));

        Assert.Equal(StatusCode.Cancelled, ex.StatusCode);
    }

    [Fact]
    public async Task Other_exceptions_pass_through_untouched()
    {
        var context = new FakeCallContext(DateTime.MaxValue, CancellationToken.None);

        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => Run(context, () => throw new InvalidOperationException("boom")));

        Assert.Equal("boom", ex.Message);
    }

    [Fact]
    public async Task A_cancellation_the_client_did_not_cause_is_not_hidden()
    {
        // An OperationCanceledException while the call's own token is NOT cancelled is a bug (e.g. an internal timeout).
        var context = new FakeCallContext(DateTime.MaxValue, CancellationToken.None);

        await Assert.ThrowsAsync<OperationCanceledException>(() => Run(context, () => throw new OperationCanceledException()));
    }

    [Fact]
    public async Task A_successful_call_returns_its_response()
    {
        var context = new FakeCallContext(DateTime.MaxValue, CancellationToken.None);

        Assert.Equal("ok", await Run(context, () => Task.FromResult("ok")));
    }
}
