using System.Text.Json;
using System.Text.Json.Serialization;

namespace Contoso.SecCopilotKit;

public sealed class TenantProfile
{
    [JsonPropertyName("licences")] public List<string> Licences { get; set; } = new();
    [JsonPropertyName("scuAvailable")] public bool ScuAvailable { get; set; }
    [JsonPropertyName("operatorRoles")] public List<string> OperatorRoles { get; set; } = new();
    [JsonPropertyName("settings")] public Dictionary<string, bool> Settings { get; set; } = new();

    public static TenantProfile Parse(string json) =>
        JsonSerializer.Deserialize<TenantProfile>(json) ?? throw new FormatException("Empty tenant profile.");
}

public enum CheckState { Met, Missing, Unknown }

public sealed record PreflightItem(CheckState State, string Requirement, string Source);

public sealed record AgentRequirement(string Kind, string Requirement, string Source, string Key);

/// <summary>
/// An offline checklist for the two agents of this episode. The tenant profile is filled by hand from the Entra admin center
/// and the Defender portal: the kit never signs in. Requirement texts and sources come from Microsoft Learn (2026-11-21).
/// </summary>
public static class Preflight
{
    public const string CaAgent = "conditional-access-optimization";
    public const string PhishingTriage = "phishing-triage";

    private const string CaUrl = "learn.microsoft.com/entra/security-copilot/conditional-access-agent-optimization";
    private const string PtUrl = "learn.microsoft.com/defender-xdr/phishing-triage-agent";

    public static IReadOnlyList<AgentRequirement> Requirements(string agent) => agent switch
    {
        CaAgent => new AgentRequirement[]
        {
            new("licence", "Microsoft Entra ID P1 (P2 includes it)", CaUrl, "EntraIdP1"),
            new("scu", "Security Compute Units available (on average under one SCU per run)", CaUrl, "scu"),
            new("role", "Security Administrator to activate the agent the first time", CaUrl, "Security Administrator"),
        },
        PhishingTriage => new AgentRequirement[]
        {
            new("licence", "Microsoft Defender for Office 365 Plan 2", PtUrl, "DefenderForOffice365P2"),
            new("scu", "Security Compute Units available (provisioned or Microsoft 365 E5/E7 inclusion)", PtUrl, "scu"),
            new("setting", "Unified RBAC activated for Defender for Office 365", PtUrl, "urbacDefenderForOffice365"),
            new("setting", "Monitor reported messages in Outlook turned on (User reported settings)", PtUrl, "monitorReportedMessages"),
            new("setting", "Alert policy 'Email reported by user as malware or phish' turned on", PtUrl, "alertPolicyReportedPhish"),
            new("setting", "Alert tuning rule 'Auto-Resolve - Email reported by user as malware or phish' disabled", PtUrl, "autoResolveTuningRuleDisabled"),
            new("role", "Security Administrator to set up, pause or remove the agent", PtUrl, "Security Administrator"),
        },
        _ => throw new ArgumentException($"Unknown agent '{agent}'. Use {CaAgent} or {PhishingTriage}.", nameof(agent)),
    };

    public static IReadOnlyList<PreflightItem> Check(string agent, TenantProfile p)
    {
        var items = new List<PreflightItem>();
        foreach (var r in Requirements(agent))
        {
            CheckState state = r.Kind switch
            {
                "licence" => HasLicence(p, r.Key) ? CheckState.Met : CheckState.Missing,
                "scu" => p.ScuAvailable ? CheckState.Met : CheckState.Missing,
                "role" => p.OperatorRoles.Contains(r.Key, StringComparer.OrdinalIgnoreCase) ? CheckState.Met : CheckState.Missing,
                "setting" => p.Settings.TryGetValue(r.Key, out var on) ? (on ? CheckState.Met : CheckState.Missing) : CheckState.Unknown,
                _ => CheckState.Unknown,
            };
            items.Add(new PreflightItem(state, r.Requirement, r.Source));
        }
        return items;
    }

    private static bool HasLicence(TenantProfile p, string key)
    {
        bool Has(string k) => p.Licences.Contains(k, StringComparer.OrdinalIgnoreCase);
        return key == "EntraIdP1" ? Has("EntraIdP1") || Has("EntraIdP2") : Has(key);
    }

    public static bool Ready(IEnumerable<PreflightItem> items) => items.All(i => i.State == CheckState.Met);
}
