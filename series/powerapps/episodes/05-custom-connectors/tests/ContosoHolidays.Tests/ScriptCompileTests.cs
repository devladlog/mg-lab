using System.Reflection;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Xunit;

namespace ContosoHolidays.Tests;

/// <summary>
/// Learn's custom code FAQ: an update fails with a bare "internal server error" when the script doesn't compile, so
/// "use the supporting classes to test compilation errors locally". The test project compiles script.csx for .NET 8,
/// which is more forgiving than the platform. This compiles it again the strict way: .NET Standard 2.0 reference
/// assemblies (Learn: "The currently supported .NET version is .NET Standard 2.0"), only the supported namespaces as
/// usings, and C# 7.3 (Learn doesn't name a C# version, so we stay conservative and refuse anything newer).
/// </summary>
public class ScriptCompileTests
{
    // Learn's supported namespaces. System.Drawing* is supported by the platform but has no .NET Standard 2.0
    // reference assembly to compile against here; the script doesn't use it.
    private static readonly string[] SupportedNamespaces =
    {
        "System", "System.Collections", "System.Collections.Generic", "System.Diagnostics", "System.IO",
        "System.IO.Compression", "System.Linq", "System.Net", "System.Net.Http", "System.Net.Http.Headers",
        "System.Net.Security", "System.Security.Authentication", "System.Security.Cryptography", "System.Text",
        "System.Text.RegularExpressions", "System.Threading", "System.Threading.Tasks", "System.Web", "System.Xml",
        "System.Xml.Linq", "Microsoft.Extensions.Logging", "Newtonsoft.Json", "Newtonsoft.Json.Linq",
    };

    private static string Metadata(string key) =>
        typeof(ScriptCompileTests).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>().Single(a => a.Key == key).Value!;

    private static IReadOnlyList<Diagnostic> CompileForPlatform(string scriptSource)
    {
        var usings = string.Join("\n", SupportedNamespaces.Select(n => $"using {n};")) + "\n";
        var stubs = File.ReadAllText(Path.Combine(FindTestDir(), "ScriptBase.cs"));
        var options = new CSharpParseOptions(LanguageVersion.CSharp7_3);
        var references = Directory.GetFiles(Metadata("NetStandardRef"), "*.dll")
            .Append(Metadata("NewtonsoftNetStandard"))
            .Append(Metadata("LoggingNetStandard"))
            .Select(p => MetadataReference.CreateFromFile(p));

        var compilation = CSharpCompilation.Create("ConnectorScript",
            new[] { CSharpSyntaxTree.ParseText(usings + scriptSource, options, "script.csx"), CSharpSyntaxTree.ParseText(stubs, options, "ScriptBase.cs") },
            references,
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));

        return compilation.GetDiagnostics().Where(d => d.Severity == DiagnosticSeverity.Error).ToList();
    }

    [Fact]
    public void The_script_compiles_for_NET_Standard_2_0_with_only_the_supported_namespaces_and_CSharp_7_3()
    {
        var errors = CompileForPlatform(File.ReadAllText(Files.Connector("script.csx.txt")));
        Assert.True(errors.Count == 0, string.Join("\n", errors));
    }

    [Theory]
    [InlineData("var x = DateOnly.FromDateTime(DateTime.Today);", "CS0103")]                // .NET 6+ API, not in .NET Standard 2.0
    [InlineData("var x = new System.Globalization.CultureInfo(\"pt-PT\").Name switch { _ => 1 };", "CS8370")] // C# 8 switch expression
    [InlineData("var x = Math.Clamp(5, 0, 2);", "CS0117")]                                   // Math.Clamp is .NET Core 2.0+, not .NET Standard 2.0
    [InlineData("var x = new JObject().ToString(Formatting.None);", "CS0104")]                 // Newtonsoft.Json.Formatting vs System.Xml.Formatting
    public void The_check_really_catches_what_the_platform_would_reject(string statement, string expectedError)
    {
        var source = "public class Script : ScriptBase { public override Task<HttpResponseMessage> ExecuteAsync() { "
                     + statement + " return Task.FromResult(new HttpResponseMessage()); } }";
        var errors = CompileForPlatform(source);
        Assert.Contains(errors, e => e.Id == expectedError);
    }

    private static string FindTestDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "ContosoHolidays.Tests.csproj"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("test project folder");
    }
}
