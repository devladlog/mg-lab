using System.Text.RegularExpressions;

namespace ModernizationScan;

/// <summary>
/// The detection table. The capability names are the scenario and skill names on Microsoft Learn,
/// ".NET scenarios and skills" (GitHub Copilot upgrade), read 21 Nov 2026. A null capability means Learn lists no
/// dedicated skill for the item: it is still a finding, and the agent handles it as an ordinary code change.
/// </summary>
public static class Rules
{
    public const string SdkStyleScenario = "SDK-style conversion (scenario)";
    public const string VersionUpgradeScenario = ".NET version upgrade (scenario)";

    public sealed record PackageRule(string IdPrefix, string What, string? Capability, string Note);

    public static readonly IReadOnlyList<PackageRule> Packages =
    [
        new("Newtonsoft.Json", "Newtonsoft.Json", "Newtonsoft.Json upgrade (scenario) / Upgrading Newtonsoft to System.Text.Json (skill)", "Replacing it changes serializer defaults: casing, numbers from strings, null input. Lock the behaviour with tests first."),
        new("System.Data.SqlClient", "System.Data.SqlClient", "SqlClient upgrade (scenario) / Upgrading to Microsoft.Data.SqlClient (skill)", "Microsoft.Data.SqlClient encrypts by default (Encrypt=true): test every connection string."),
        new("EntityFramework", "Entity Framework 6", "Upgrading EF6 Code-First to EF Core (skill)", "EDMX models use the EDMX skill instead."),
        new("Autofac", "Autofac", "Upgrading Autofac to .NET DI (skill) / Integrating Autofac with .NET (skill)", "Choose: drop Autofac or keep it."),
        new("Microsoft.AspNet.Mvc", "ASP.NET MVC 5", "Upgrading ASP.NET Framework to Core (skill)", "Orchestrates the other web skills."),
        new("Microsoft.AspNet.WebApi.Cors", "Web API CORS", "Upgrading WebAPI CORS (skill)", ""),
        new("Microsoft.AspNet.WebApi.OData", "Web API OData", "Upgrading WebAPI OData (skill)", ""),
        new("Microsoft.AspNet.SignalR", "ASP.NET SignalR 2.x", "Upgrading ASP.NET SignalR (skill)", ""),
        new("Microsoft.Owin.Security.Cookies", "OWIN cookie authentication", "Upgrading OWIN Cookie Authentication (skill)", ""),
        new("Microsoft.Owin.Security.OAuth", "OWIN OAuth bearer", "Upgrading OWIN OAuth to JWT (skill)", ""),
        new("Microsoft.Owin.Security.OpenIdConnect", "OWIN OpenID Connect", "Upgrading OWIN OpenID Connect (skill)", ""),
        new("Microsoft.IdentityModel.Clients.ActiveDirectory", "ADAL", "Upgrading ADAL to MSAL (skill)", ""),
        new("WindowsAzure.Storage", "WindowsAzure.Storage", "Upgrading Azure Storage (skill)", ""),
        new("WindowsAzure.ServiceBus", "WindowsAzure.ServiceBus", "Upgrading Azure Service Bus (skill)", ""),
        new("Microsoft.Azure.KeyVault", "Microsoft.Azure.KeyVault", "Upgrading Azure Key Vault (skill)", ""),
        new("Microsoft.Azure.DocumentDB", "DocumentDB SDK", "Upgrading DocumentDB to Cosmos DB (skill)", ""),
        new("RazorEngine", "RazorEngine", "Upgrading RazorEngine to RazorLight (skill)", ""),
    ];

    public sealed record CodeRule(string Name, Regex Pattern, string[] Extensions, string What, string? Capability, string Note);

    public static readonly IReadOnlyList<CodeRule> Code =
    [
        new("httpcontext-current", new(@"\bHttpContext\.Current\b"), [".cs", ".cshtml"], "HttpContext.Current", "Upgrading MVC HttpContext (skill)", "No static HttpContext in ASP.NET Core."),
        new("global-asax", new(@"\bApplication_(Start|Error|BeginRequest|EndRequest)\b"), [".cs"], "Global.asax lifecycle events", "Upgrading Global.asax (skill)", "Moves to Program.cs and middleware."),
        new("route-collection", new(@"\bRouteTable\.Routes\b|\bRouteCollection\b"), [".cs"], "RouteCollection routing", "Upgrading MVC routing (skill)", ""),
        new("session", new(@"\bSession\["), [".cs", ".cshtml"], "Session state", "Upgrading MVC session state (skill)", "ISession needs a cache backend."),
        new("bundling", new(@"System\.Web\.Optimization"), [".cs", ".cshtml"], "System.Web.Optimization bundling", "Upgrading MVC bundling (skill)", ""),
        new("http-pipeline", new(@":\s*(IHttpModule|IHttpHandler)\b"), [".cs"], "IHttpModule / IHttpHandler", "Upgrading MVC HTTP pipeline (skill)", ""),
        new("wcf", new(@"\[ServiceContract\]|System\.ServiceModel"), [".cs", ".config"], "WCF service", "Upgrading WCF to CoreWCF (skill)", "Server side only."),
        new("msmq", new(@"System\.Messaging"), [".cs"], "System.Messaging (MSMQ)", "Upgrading to MSMQ.Messaging (skill)", ""),
        new("mvc-controllers", new(@":\s*(Controller|ApiController)\b"), [".cs"], "MVC / Web API controllers", "Upgrading MVC controllers (skill)", ""),
        new("sqlclient-code", new(@"using System\.Data\.SqlClient;"), [".cs"], "using System.Data.SqlClient", "Upgrading to Microsoft.Data.SqlClient (skill)", "Namespace swap; connection defaults differ."),
        new("web-config", new(@"<system\.web>|<system\.webServer>"), [".config"], "web.config sections", "Upgrading MVC configuration (skill)", "Settings move to appsettings.json and IConfiguration."),
        new("binaryformatter", new(@"\bBinaryFormatter\b"), [".cs"], "BinaryFormatter", null, "Removed from modern .NET (it appears as a breaking change in Learn's sample plan); no dedicated skill listed."),
    ];

    /// <summary>
    /// Learn's WPF and Windows Forms upgrade articles use a sample that targets .NET Framework 4.5: Visual Studio shows
    /// "Target Framework Not Installed" and offers to retarget to 4.8, and the article says to commit that first.
    /// Below 4.6.2 is our cut-off for flagging it; Learn does not state one.
    /// </summary>
    public static bool OldFramework(string tfm) =>
        tfm.StartsWith("net4", StringComparison.Ordinal) && int.TryParse(tfm.AsSpan(3).ToString().PadRight(3, '0'), out var n) && n < 462; // net45 -> 450, net48 -> 480, net472 -> 472
}
