namespace TenantApi.Tests;

static class Paths
{
    public static string Root { get; } = FindRoot();

    static string FindRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !(Directory.Exists(Path.Combine(dir.FullName, "sql")) && Directory.Exists(Path.Combine(dir.FullName, "src"))))
            dir = dir.Parent;
        return dir?.FullName ?? throw new InvalidOperationException("Episode root not found.");
    }

    public static string Of(params string[] parts) => Path.Combine([Root, .. parts]);
}
