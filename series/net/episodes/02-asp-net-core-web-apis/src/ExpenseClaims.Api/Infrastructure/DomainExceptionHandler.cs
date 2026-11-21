using ExpenseClaims.Api.Claims;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Mvc;

namespace ExpenseClaims.Api.Infrastructure;

/// <summary>
/// Registered with AddExceptionHandler and run by UseExceptionHandler. Known domain errors become 404/409
/// problem details; anything else returns false and falls through to the default 500 problem response.
/// </summary>
public sealed class DomainExceptionHandler(IProblemDetailsService problemDetails, ILogger<DomainExceptionHandler> logger)
    : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(HttpContext httpContext, Exception exception, CancellationToken cancellationToken)
    {
        if (exception is not DomainException domain)
            return false;

        logger.LogInformation("Domain rule rejected {Path}: {Title}", httpContext.Request.Path, domain.Title);

        httpContext.Response.StatusCode = domain.StatusCode;
        return await problemDetails.TryWriteAsync(new ProblemDetailsContext
        {
            HttpContext = httpContext,
            Exception = exception,
            ProblemDetails = new ProblemDetails
            {
                Status = domain.StatusCode,
                Title = domain.Title,
                Detail = domain.Message,
            },
        });
    }
}
