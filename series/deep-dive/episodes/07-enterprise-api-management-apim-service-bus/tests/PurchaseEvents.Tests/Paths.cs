namespace PurchaseEvents.Tests;

internal static class Paths
{
    /// <summary>The episode folder: the first parent of the test assembly that contains apim/ and infra/.</summary>
    public static readonly string EpisodeRoot = Find();

    private static string Find()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !(Directory.Exists(Path.Combine(dir.FullName, "apim")) && Directory.Exists(Path.Combine(dir.FullName, "infra"))))
            dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("episode root not found");
    }
}
