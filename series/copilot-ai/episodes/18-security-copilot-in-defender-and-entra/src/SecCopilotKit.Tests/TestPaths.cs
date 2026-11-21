namespace Contoso.SecCopilotKit.Tests;

internal static class TestPaths
{
    public static readonly string Root = FindRoot();
    public static string File(params string[] parts) => Path.Combine(new[] { Root }.Concat(parts).ToArray());
    public static string Read(params string[] parts) => System.IO.File.ReadAllText(File(parts));

    private static string FindRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !System.IO.File.Exists(Path.Combine(dir.FullName, "plugin", "contoso-soc-hunting.yaml"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("Episode folder not found above " + AppContext.BaseDirectory);
    }
}
