using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace ExpenseClaims.Api.Tests;

/// <summary>
/// The App Service app settings from deploy-appservice.sh (Authentication__Schemes__Bearer__*) must land in
/// JwtBearerOptions without any code. This checks the binding with the same keys (':' == '__').
/// </summary>
public class ConfigurationTests
{
    [Fact]
    public void Entra_settings_bind_to_the_bearer_options()
    {
        const string tenant = "00000000-0000-0000-0000-000000000000";
        using var factory = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseEnvironment("Production");
            b.UseSetting("Authentication:Schemes:Bearer:Authority", $"https://sts.windows.net/{tenant}/");
            b.UseSetting("Authentication:Schemes:Bearer:ValidAudiences:0", $"api://{tenant}");
        });

        var options = factory.Services.GetRequiredService<IOptionsMonitor<JwtBearerOptions>>()
            .Get(JwtBearerDefaults.AuthenticationScheme);

        Assert.Equal($"https://sts.windows.net/{tenant}/", options.Authority);
        Assert.Contains($"api://{tenant}", options.TokenValidationParameters.ValidAudiences);
        Assert.False(options.MapInboundClaims);
        Assert.Equal("roles", options.TokenValidationParameters.RoleClaimType);
    }
}
