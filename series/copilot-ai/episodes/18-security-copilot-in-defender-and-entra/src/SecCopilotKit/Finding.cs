namespace Contoso.SecCopilotKit;

public enum Severity { Info, Warning, Error }

/// <summary>One result of a check. Path points into the manifest, for example SkillGroups[0].Skills[1].Name.</summary>
public sealed record Finding(Severity Severity, string Path, string Message)
{
    public override string ToString() => $"{Severity.ToString().ToUpperInvariant(),-7} {Path}: {Message}";
}

public static class FindingExtensions
{
    public static int Errors(this IEnumerable<Finding> f) => f.Count(x => x.Severity == Severity.Error);
    public static int Warnings(this IEnumerable<Finding> f) => f.Count(x => x.Severity == Severity.Warning);
}
