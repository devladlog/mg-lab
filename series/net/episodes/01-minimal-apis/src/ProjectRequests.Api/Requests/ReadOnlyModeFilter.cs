namespace ProjectRequests.Api.Requests;

/// <summary>
/// Endpoint filter for the write endpoints: when "Api:ReadOnly" is true (for example during a migration),
/// writes get a 503 problem response and the handler never runs. Reads keep working.
/// </summary>
public sealed class ReadOnlyModeFilter(IConfiguration configuration) : IEndpointFilter
{
    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        if (configuration.GetValue<bool>("Api:ReadOnly"))
        {
            context.HttpContext.Response.Headers.RetryAfter = "120";
            return TypedResults.Problem(
                title: "The API is in read-only mode.",
                detail: "Writes are paused for maintenance. Try again later.",
                statusCode: StatusCodes.Status503ServiceUnavailable);
        }

        return await next(context);
    }
}
