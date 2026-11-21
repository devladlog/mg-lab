using System.ComponentModel.DataAnnotations;

namespace Contoso.Approvals.Patterns;

/// <summary>Options pattern: the policy lives in configuration ("Policy" section) and is validated at startup.</summary>
public sealed class ApprovalPolicyOptions
{
    public const string SectionName = "Policy";

    [Range(typeof(decimal), "1", "1000000000")]
    public decimal HighThreshold { get; set; } = 50_000m;

    [Range(typeof(decimal), "1", "1000000000")]
    public decimal BoardThreshold { get; set; } = 250_000m;

    [Range(1, 90)]
    public int StandardDueDays { get; set; } = 5;

    [Range(1, 90)]
    public int HighDueDays { get; set; } = 10;

    [Range(1, 90)]
    public int BoardDueDays { get; set; } = 20;
}

public sealed class ApproverDirectoryOptions
{
    public const string SectionName = "Directory";

    [Required]
    public string File { get; set; } = "samples/approvers.json";

    [Range(0, 86_400)]
    public int CacheSeconds { get; set; } = 300;
}

public sealed class OutboxOptions
{
    public const string SectionName = "Outbox";

    [Required]
    public string Folder { get; set; } = "outbox";
}
