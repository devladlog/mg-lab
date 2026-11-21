namespace Contoso.Mobile.Tests;

/// <summary>Finds files of the MAUI app project from the test's output folder (the tests run inside the repository).</summary>
public static class Repo
{
    public static string Root { get; } = FindRoot();

    public static string Path(string relative) => System.IO.Path.Combine(Root, relative.Replace('/', System.IO.Path.DirectorySeparatorChar));

    private static string FindRoot()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
            if (File.Exists(System.IO.Path.Combine(dir.FullName, "Contoso.Mobile.slnx"))) return dir.FullName;
        throw new InvalidOperationException("Contoso.Mobile.slnx not found above " + AppContext.BaseDirectory);
    }
}
