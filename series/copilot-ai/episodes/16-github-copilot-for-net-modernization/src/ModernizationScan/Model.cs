namespace ModernizationScan;

public sealed record PackageRef(string Id, string Version);

public sealed record ProjectInfo(
    string Name,
    string Path,
    bool IsSdkStyle,
    string TargetFramework,
    bool UsesPackagesConfig,
    bool IsWebApplication,
    IReadOnlyList<string> ProjectReferences,
    IReadOnlyList<PackageRef> Packages);

/// <summary>One thing the agent will have to deal with, and the Learn scenario or skill that covers it (if there is one).</summary>
public sealed record Finding(string Project, string Kind, string What, string Evidence, string? LearnCapability, string Note);

public sealed record Report(
    string Root,
    IReadOnlyList<ProjectInfo> Projects,
    IReadOnlyList<string> UpgradeOrder,
    IReadOnlyList<Finding> Findings,
    string SuggestedStrategy,
    int Score,
    string Readiness,
    IReadOnlyList<string> Warnings);
