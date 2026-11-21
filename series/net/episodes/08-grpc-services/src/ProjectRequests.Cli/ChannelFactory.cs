using Grpc.Core;
using Grpc.Net.Client;
using Grpc.Net.Client.Configuration;
using ProjectRequests.Grpc;

namespace ProjectRequests.Cli;

public static class ChannelFactory
{
    /// <summary>Package + service name from requests.proto ("package projectrequests.v1; service Requests").</summary>
    public const string ServiceName = "projectrequests.v1.Requests";

    /// <summary>
    /// One channel per address, reused for every call (it owns the HTTP/2 connection). Retries are configured
    /// ONCE here, in the service config, and only for the two read methods: a retried ImportRequests could
    /// create the same requests twice (the call isn't idempotent), so it gets no retry policy.
    /// </summary>
    public static GrpcChannel Create(Uri address, HttpMessageHandler? handler = null)
    {
        var retryReads = new RetryPolicy
        {
            MaxAttempts = 3,
            InitialBackoff = TimeSpan.FromMilliseconds(200),
            MaxBackoff = TimeSpan.FromSeconds(2),
            BackoffMultiplier = 2,
            RetryableStatusCodes = { StatusCode.Unavailable },
        };

        return GrpcChannel.ForAddress(address, new GrpcChannelOptions
        {
            HttpHandler = handler,
            ServiceConfig = new ServiceConfig
            {
                MethodConfigs =
                {
                    new MethodConfig { Names = { new MethodName { Service = ServiceName, Method = "GetRequest" } }, RetryPolicy = retryReads },
                    new MethodConfig { Names = { new MethodName { Service = ServiceName, Method = "ListRequests" } }, RetryPolicy = retryReads },
                },
            },
        });
    }
}
