using Grpc.Core;
using Grpc.Core.Interceptors;

namespace ProjectRequests.Api.Rpc;

/// <summary>
/// A server interceptor: runs around every service method. When the client's deadline passes or the client cancels,
/// the call's token fires and awaiting code throws OperationCanceledException. Left alone, that surfaces as an
/// "Unknown ... Exception was thrown by handler" status (and an error-level log line). Mapping it gives the call the
/// status it really ended with, as far as the server can know: its own deadline has passed, or the client went away
/// (which includes a client whose own, slightly earlier, deadline expired).
/// </summary>
public sealed class CancellationStatusInterceptor(ILogger<CancellationStatusInterceptor> logger) : Interceptor
{
    public override Task<TResponse> UnaryServerHandler<TRequest, TResponse>(
        TRequest request, ServerCallContext context, UnaryServerMethod<TRequest, TResponse> continuation) =>
        Map(context, () => continuation(request, context));

    public override Task<TResponse> ClientStreamingServerHandler<TRequest, TResponse>(
        IAsyncStreamReader<TRequest> requestStream, ServerCallContext context, ClientStreamingServerMethod<TRequest, TResponse> continuation) =>
        Map(context, () => continuation(requestStream, context));

    public override Task ServerStreamingServerHandler<TRequest, TResponse>(
        TRequest request, IServerStreamWriter<TResponse> responseStream, ServerCallContext context, ServerStreamingServerMethod<TRequest, TResponse> continuation) =>
        Map(context, async () => { await continuation(request, responseStream, context); return 0; });

    private async Task<T> Map<T>(ServerCallContext context, Func<Task<T>> next)
    {
        try
        {
            return await next();
        }
        catch (OperationCanceledException) when (context.CancellationToken.IsCancellationRequested)
        {
            var deadlineExceeded = context.Deadline <= DateTime.UtcNow;       // Deadline is UTC; DateTime.MaxValue = none
            logger.LogInformation("{Method} ended early: {Reason}", context.Method, deadlineExceeded ? "deadline exceeded" : "cancelled by the client");
            throw new RpcException(deadlineExceeded
                ? new Status(StatusCode.DeadlineExceeded, "Deadline exceeded.")
                : new Status(StatusCode.Cancelled, "Cancelled by the client."));
        }
    }
}
