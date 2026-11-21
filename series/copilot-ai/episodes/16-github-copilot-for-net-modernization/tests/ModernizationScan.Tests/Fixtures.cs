namespace ModernizationScan.Tests;

internal static class Fixtures
{
    public static string EpisodeRoot { get; } = FindEpisodeRoot();

    public static string Legacy => Path.Combine(EpisodeRoot, "src", "legacy-contoso");
    public static string ExpectedAfter => Path.Combine(EpisodeRoot, "src", "expected-after");

    private static string FindEpisodeRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !Directory.Exists(Path.Combine(dir.FullName, "src", "legacy-contoso"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("episode root not found above " + AppContext.BaseDirectory);
    }

    /// <summary>A throwaway folder that is deleted when disposed.</summary>
    public sealed class Temp : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "modscan-" + Guid.NewGuid().ToString("N"));
        public Temp() => Directory.CreateDirectory(Path);
        public string Write(string relative, string content)
        {
            var full = System.IO.Path.Combine(Path, relative);
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(full)!);
            File.WriteAllText(full, content);
            return full;
        }
        public void Dispose() => Directory.Delete(Path, recursive: true);
    }

    public static string LegacyProject(string refs = "", string tfv = "v4.7.2", string extra = "") => $"""
        <Project ToolsVersion="15.0" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
          <PropertyGroup><TargetFrameworkVersion>{tfv}</TargetFrameworkVersion>{extra}</PropertyGroup>
          <ItemGroup>{refs}</ItemGroup>
        </Project>
        """;

    public static string ProjectRef(string name) => $"<ProjectReference Include=\"..\\{name}\\{name}.csproj\" />";

    public static string Sdk(string body = "", string tfm = "net10.0") => $"""
        <Project Sdk="Microsoft.NET.Sdk">
          <PropertyGroup><TargetFramework>{tfm}</TargetFramework></PropertyGroup>
          {body}
        </Project>
        """;
}
