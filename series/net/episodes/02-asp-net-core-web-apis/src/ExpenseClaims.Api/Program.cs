using System.Globalization;
using System.Text.Json.Serialization;
using System.Threading.RateLimiting;
using ExpenseClaims.Api.Claims;
using ExpenseClaims.Api.Infrastructure;
using Microsoft.AspNetCore.Authentication.JwtBearer;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers()
    .AddJsonOptions(o => o.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter()));
builder.Services.AddOpenApi();
builder.Services.AddProblemDetails();
builder.Services.AddExceptionHandler<DomainExceptionHandler>();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<ClaimWorkflow>();

// Authority, ValidAudiences, ValidIssuer and (for user-jwts) SigningKeys come from
// configuration: Authentication:Schemes:Bearer. Locally: dotnet user-jwts. In Azure: Microsoft Entra ID.
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        o.MapInboundClaims = false;                          // keep "roles", "oid", "sub" as they are in the JWT
        o.TokenValidationParameters.RoleClaimType = "roles"; // Entra app roles arrive in the "roles" claim
        o.TokenValidationParameters.NameClaimType = "name";
    });

builder.Services.AddAuthorizationBuilder()
    .AddPolicy("Approver", p => p.RequireRole(CurrentUser.ApproverRole));

builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = StatusCodes.Status429TooManyRequests;   // the default is 503
    // One window per user, not one for the whole API. The limit is read from configuration (default 5).
    o.AddPolicy("submit", http => RateLimitPartition.GetFixedWindowLimiter(
        http.User.FindFirst("oid")?.Value ?? http.User.FindFirst("sub")?.Value ?? "anonymous",
        _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = http.RequestServices.GetRequiredService<IConfiguration>().GetValue("RateLimits:SubmitPerMinute", 5),
            Window = TimeSpan.FromMinutes(1),
        }));

    o.OnRejected = async (ctx, ct) =>
    {
        if (ctx.Lease.TryGetMetadata(MetadataName.RetryAfter, out var retryAfter))
            ctx.HttpContext.Response.Headers.RetryAfter =
                ((int)retryAfter.TotalSeconds).ToString(CultureInfo.InvariantCulture);

        await ctx.HttpContext.RequestServices.GetRequiredService<IProblemDetailsService>().WriteAsync(new()
        {
            HttpContext = ctx.HttpContext,
            ProblemDetails = { Title = "Too many claims submitted.", Status = StatusCodes.Status429TooManyRequests },
        });
    };
});

var app = builder.Build();

app.UseExceptionHandler();
app.UseStatusCodePages();

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseAuthentication();
app.UseAuthorization();
app.UseRateLimiter();        // after authentication, so the partition key (the user) is known

app.MapControllers();
app.MapGet("/healthz", () => "Healthy").AllowAnonymous();

app.Run();
