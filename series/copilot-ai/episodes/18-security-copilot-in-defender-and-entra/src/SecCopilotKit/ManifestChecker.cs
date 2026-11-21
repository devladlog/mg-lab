using System.Text.Json.Nodes;

namespace Contoso.SecCopilotKit;

/// <summary>
/// Checks a Security Copilot plugin or agent manifest against the rules in Microsoft Learn (Agent manifest, KQL plugins,
/// 2026-11-21): required keys, name constraints, formats and settings per format, input/placeholder agreement, agent
/// definitions and triggers, and every KQL template through <see cref="KqlChecker"/>.
/// </summary>
public static class ManifestChecker
{
    private static readonly string[] Formats = { "API", "GPT", "AGENT", "KQL", "LogicApp" };
    private static readonly string[] Targets = { "Defender", "Sentinel", "SentinelDataLake", "LogAnalytics", "Kusto" };
    private static readonly string[] AuthTypes =
        { "None", "Basic", "ApiKey", "ServiceHttp", "OAuthAuthorizationCodeFlow", "OAuthClientCredentialsFlow", "OAuthPasswordGrantFlow", "AAD", "AADDelegated" };
    private static readonly string[] Constraints = { "None", "Workspace", "Tenant" };
    private static readonly char[] DescriptorForbidden = { '/', ',', '\\', '?', '#', '@' };

    public static IReadOnlyList<Finding> Check(JsonNode root)
    {
        var f = new List<Finding>();
        if (root is not JsonObject top) { f.Add(new(Severity.Error, "$", "the manifest must be a mapping with Descriptor and SkillGroups.")); return f; }

        foreach (var key in top.Select(kv => kv.Key))
            if (key is not ("Descriptor" or "SkillGroups" or "AgentDefinitions"))
                f.Add(new(Severity.Warning, key, "unknown top-level key (Learn lists Descriptor, SkillGroups, AgentDefinitions)."));

        var descriptor = top["Descriptor"] as JsonObject;
        var groups = top["SkillGroups"] as JsonArray;
        if (descriptor is null) f.Add(new(Severity.Error, "Descriptor", "required."));
        if (groups is null) f.Add(new(Severity.Error, "SkillGroups", "required."));

        string descriptorName = "";
        var descriptorSettings = new HashSet<string>(StringComparer.Ordinal);
        if (descriptor is not null)
        {
            descriptorName = Str(descriptor["Name"]);
            CheckDescriptor(descriptor, descriptorName, f);
            if (descriptor["Settings"] is JsonArray ds)
                foreach (var s in ds.OfType<JsonObject>()) descriptorSettings.Add(Str(s["Name"]));
        }

        var skills = new Dictionary<string, (JsonObject Skill, string Format, string Path)>(StringComparer.Ordinal);
        bool hasApi = false;
        if (groups is not null)
        {
            for (int i = 0; i < groups.Count; i++)
            {
                if (groups[i] is not JsonObject g) { f.Add(new(Severity.Error, $"SkillGroups[{i}]", "must be a mapping.")); continue; }
                var format = Str(g["Format"]);
                var gp = $"SkillGroups[{i}]";
                if (!Formats.Contains(format)) { f.Add(new(Severity.Error, gp + ".Format", $"'{format}' is not one of {string.Join(", ", Formats)}.")); continue; }
                if (format == "API") hasApi = true;
                var list = g["Skills"] as JsonArray;
                if (list is null)
                {
                    // Learn's API quickstart has no Skills (the OpenAPI operations become the tools); the other formats need them.
                    if (format != "API" && format != "LogicApp") f.Add(new(Severity.Error, gp + ".Skills", $"required for Format {format}."));
                    continue;
                }
                for (int j = 0; j < list.Count; j++)
                {
                    var sp = $"{gp}.Skills[{j}]";
                    if (list[j] is not JsonObject skill) { f.Add(new(Severity.Error, sp, "must be a mapping.")); continue; }
                    var name = Str(skill["Name"]);
                    if (name.Length > 0 && !skills.TryAdd(name, (skill, format, sp)))
                        f.Add(new(Severity.Error, sp + ".Name", $"'{name}' is used twice; skill names must be unique."));
                    CheckSkill(skill, format, g, sp, descriptorSettings, f);
                }
            }
        }

        if (hasApi)
        {
            if (descriptor?["SupportedAuthTypes"] is not JsonArray sat || sat.Count == 0)
                f.Add(new(Severity.Error, "Descriptor.SupportedAuthTypes", "required when a skill group has Format API (Learn)."));
        }

        // Agent skills: ChildSkills must be skills of this manifest, or come from another skillset in RequiredSkillsets.
        var external = new HashSet<string>(StringComparer.Ordinal);
        if (top["AgentDefinitions"] is JsonArray ad)
            foreach (var d in ad.OfType<JsonObject>())
                if (d["RequiredSkillsets"] is JsonArray rsets)
                    foreach (var r in rsets) if (Str(r) != descriptorName) external.Add(Str(r));
        foreach (var (name, (skill, format, path)) in skills.Where(kv => kv.Value.Format == "AGENT"))
        {
            if (skill["ChildSkills"] is JsonArray cs)
                for (int k = 0; k < cs.Count; k++)
                {
                    var child = Str(cs[k]);
                    if (skills.ContainsKey(child)) continue;
                    if (external.Count > 0)
                        f.Add(new(Severity.Info, $"{path}.ChildSkills[{k}]",
                            $"'{child}' is not in this manifest; it must exist in one of: {string.Join(", ", external)} (not checkable offline)."));
                    else
                        f.Add(new(Severity.Error, $"{path}.ChildSkills[{k}]",
                            $"'{child}' is not a skill of this manifest and RequiredSkillsets lists no other skillset to provide it."));
                }
        }

        if (top["AgentDefinitions"] is JsonArray defs)
            for (int i = 0; i < defs.Count; i++) CheckAgentDefinition(defs[i] as JsonObject, $"AgentDefinitions[{i}]", descriptorName, skills, f);

        return f;
    }

    public static IReadOnlyList<Finding> CheckText(string yaml)
    {
        try { return Check(YamlLoader.Parse(yaml)); }
        catch (Exception e) when (e is YamlDotNet.Core.YamlException or FormatException)
        { return new[] { new Finding(Severity.Error, "$", "not valid YAML: " + e.Message) }; }
    }

    // ---- Descriptor -------------------------------------------------------------------------------------------------
    private static void CheckDescriptor(JsonObject d, string name, List<Finding> f)
    {
        if (name.Length == 0) f.Add(new(Severity.Error, "Descriptor.Name", "required."));
        else
        {
            if (name.Any(char.IsWhiteSpace)) f.Add(new(Severity.Error, "Descriptor.Name", "cannot contain whitespace."));
            if (name.IndexOfAny(DescriptorForbidden) >= 0) f.Add(new(Severity.Error, "Descriptor.Name", "cannot contain / , \\ ? # @ (Learn)."));
        }
        if (Str(d["Description"]).Length == 0) f.Add(new(Severity.Error, "Descriptor.Description", "required and cannot be empty."));
        if (Str(d["DisplayName"]).Length == 0) f.Add(new(Severity.Warning, "Descriptor.DisplayName", "recommended."));
        if (d["SupportedAuthTypes"] is JsonArray sat)
            for (int i = 0; i < sat.Count; i++)
                if (!AuthTypes.Contains(Str(sat[i]))) f.Add(new(Severity.Error, $"Descriptor.SupportedAuthTypes[{i}]", $"'{Str(sat[i])}' is not a supported scheme."));
    }

    // ---- Skills -----------------------------------------------------------------------------------------------------
    private static void CheckSkill(JsonObject skill, string format, JsonObject group, string path, HashSet<string> descriptorSettings, List<Finding> f)
    {
        var name = Str(skill["Name"]);
        if (name.Length == 0) f.Add(new(Severity.Error, path + ".Name", "required."));
        else if (name.Any(char.IsWhiteSpace) || name.Contains('.')) f.Add(new(Severity.Error, path + ".Name", "cannot contain whitespace or a period (Learn)."));
        if (skill.ContainsKey("Description") && Str(skill["Description"]).Length == 0) f.Add(new(Severity.Error, path + ".Description", "cannot be empty."));
        else if (!skill.ContainsKey("Description")) f.Add(new(Severity.Warning, path + ".Description", "recommended: the model chooses skills by their description."));
        if (Str(skill["DisplayName"]).Length == 0) f.Add(new(Severity.Warning, path + ".DisplayName", "recommended."));

        var inputs = new Dictionary<string, bool>(StringComparer.Ordinal);
        if (skill["Inputs"] is JsonArray ins)
            for (int i = 0; i < ins.Count; i++)
            {
                if (ins[i] is not JsonObject inp) continue;
                var iname = Str(inp["Name"]);
                if (iname.Length == 0) f.Add(new(Severity.Error, $"{path}.Inputs[{i}].Name", "required."));
                if (Str(inp["Description"]).Length == 0) f.Add(new(Severity.Warning, $"{path}.Inputs[{i}].Description", "describe the input: the model fills it from the description."));
                inputs[iname] = Str(inp["Required"]).Equals("true", StringComparison.OrdinalIgnoreCase);
            }

        var settings = skill["Settings"] as JsonObject;
        if (settings is null) { f.Add(new(Severity.Error, path + ".Settings", "required.")); return; }
        var sp = path + ".Settings";

        string? template = null;
        switch (format)
        {
            case "KQL":
            {
                var target = Str(settings["Target"]);
                if (target.Length == 0) f.Add(new(Severity.Error, sp + ".Target", "required."));
                else if (!Targets.Contains(target)) f.Add(new(Severity.Error, sp + ".Target", $"'{target}' is not one of {string.Join(", ", Targets)}."));
                template = Str(settings["Template"]);
                var hasUrl = Str(settings["TemplateUrl"]).Length > 0;
                var hasPackage = Str(group["Settings"]?["PackageUrl"]).Length > 0 || Str(settings["PackageUrl"]).Length > 0;
                if (template.Length > 0 && hasUrl) f.Add(new(Severity.Error, sp, "specify either Template or TemplateUrl, not both."));
                if (template.Length == 0 && !hasUrl && !hasPackage) f.Add(new(Severity.Error, sp + ".Template", "required when TemplateUrl and PackageUrl are not given."));
                if (target == "Kusto")
                    foreach (var req in new[] { "Cluster", "Database" })
                        if (Str(settings[req]).Length == 0) f.Add(new(Severity.Error, $"{sp}.{req}", "required for Target Kusto."));
                if (target == "Sentinel")
                    foreach (var req in new[] { "TenantId", "SubscriptionId", "ResourceGroupName", "WorkspaceName" })
                        if (Str(settings[req]).Length == 0) f.Add(new(Severity.Error, $"{sp}.{req}", "required for Target Sentinel."));
                if (template.Length > 0 && Targets.Contains(target))
                    f.AddRange(KqlChecker.Check(template, sp + ".Template", target).Findings);
                break;
            }
            case "GPT":
            {
                var model = Str(settings["ModelName"]);
                if (model.Length == 0) f.Add(new(Severity.Error, sp + ".ModelName", "required."));
                else if (model != "gpt-4.1") f.Add(new(Severity.Error, sp + ".ModelName", $"'{model}': Learn says ModelName must be gpt-4.1."));
                template = Str(settings["Template"]);
                if (template.Length == 0) f.Add(new(Severity.Error, sp + ".Template", "required."));
                else if (template.Length > KqlChecker.MaxTemplateChars) f.Add(new(Severity.Error, sp + ".Template", $"over {KqlChecker.MaxTemplateChars} characters."));
                break;
            }
            case "AGENT":
            {
                template = Str(settings["Instructions"]);
                if (template.Length == 0) f.Add(new(Severity.Error, sp + ".Instructions", "required."));
                if (skill["ChildSkills"] is not JsonArray { Count: > 0 }) f.Add(new(Severity.Warning, path + ".ChildSkills", "an agent without child skills has nothing to call."));
                break;
            }
        }

        if (template is { Length: > 0 })
        {
            var used = TemplateRenderer.Placeholders(template);
            foreach (var u in used)
                if (!inputs.ContainsKey(u) && !descriptorSettings.Contains(u) && !settings.ContainsKey(u))
                    f.Add(new(Severity.Error, path, $"placeholder {{{{{u}}}}} has no matching Inputs entry."));
            foreach (var kv in inputs)
                if (kv.Key.Length > 0 && !used.Contains(kv.Key))
                    f.Add(new(Severity.Warning, $"{path}.Inputs", $"input '{kv.Key}' is never used in the template."));
        }
    }

    // ---- Agent definitions ------------------------------------------------------------------------------------------
    private static void CheckAgentDefinition(JsonObject? def, string path, string descriptorName,
        Dictionary<string, (JsonObject Skill, string Format, string Path)> skills, List<Finding> f)
    {
        if (def is null) { f.Add(new(Severity.Error, path, "must be a mapping.")); return; }
        var name = Str(def["Name"]);
        if (name.Length == 0 || name.Any(char.IsWhiteSpace) || name.Contains('.'))
            f.Add(new(Severity.Error, path + ".Name", "required; cannot contain whitespace or a period."));
        foreach (var req in new[] { "DisplayName", "Description", "Publisher", "Product" })
            if (Str(def[req]).Length == 0) f.Add(new(Severity.Error, $"{path}.{req}", "required."));

        var rs = def["RequiredSkillsets"] as JsonArray;
        if (rs is null || rs.Count == 0) f.Add(new(Severity.Error, path + ".RequiredSkillsets", "required."));
        else if (descriptorName.Length > 0 && !rs.Select(Str).Contains(descriptorName))
            f.Add(new(Severity.Warning, path + ".RequiredSkillsets", $"does not list this manifest's own skillset '{descriptorName}'."));

        var c = Str(def["AgentSingleInstanceConstraint"]);
        if (c.Length > 0 && !Constraints.Contains(c)) f.Add(new(Severity.Error, path + ".AgentSingleInstanceConstraint", $"'{c}' is not None, Workspace or Tenant."));

        if (def["Settings"] is JsonArray st)
            for (int i = 0; i < st.Count; i++)
                if (st[i] is JsonObject s)
                    foreach (var req in new[] { "Name", "SettingType" })
                        if (Str(s[req]).Length == 0) f.Add(new(Severity.Error, $"{path}.Settings[{i}].{req}", "required."));

        if (def["Triggers"] is not JsonArray { Count: > 0 } triggers)
        { f.Add(new(Severity.Error, path + ".Triggers", "at least one trigger is required (Learn).")); return; }

        for (int i = 0; i < triggers.Count; i++)
        {
            var tp = $"{path}.Triggers[{i}]";
            if (triggers[i] is not JsonObject t) { f.Add(new(Severity.Error, tp, "must be a mapping.")); continue; }
            var tn = Str(t["Name"]);
            if (tn.Length == 0 || tn.Any(char.IsWhiteSpace)) f.Add(new(Severity.Error, tp + ".Name", "required; cannot contain whitespace."));
            var period = Str(t["DefaultPeriodSeconds"]);
            if (period.Length > 0 && (!int.TryParse(period, out var secs) || secs < 0))
                f.Add(new(Severity.Error, tp + ".DefaultPeriodSeconds", "must be a whole number of seconds, 0 or more (0 disables scheduled runs)."));
            var process = Str(t["ProcessSkill"]);
            if (process.Length == 0) f.Add(new(Severity.Error, tp + ".ProcessSkill", "required."));
            var fetch = Str(t["FetchSkill"]);

            var processLocal = Resolve(process, descriptorName, skills);
            var fetchLocal = fetch.Length > 0 ? Resolve(fetch, descriptorName, skills) : null;
            if (process.Length > 0 && IsOwn(process, descriptorName) && processLocal is null)
                f.Add(new(Severity.Error, tp + ".ProcessSkill", $"'{process}' does not name a skill of this manifest."));
            if (fetch.Length > 0 && IsOwn(fetch, descriptorName) && fetchLocal is null)
                f.Add(new(Severity.Error, tp + ".FetchSkill", $"'{fetch}' does not name a skill of this manifest."));

            // Learn: the trigger calls ProcessSkill with the values of each object FetchSkill returns as its inputs.
            if (processLocal is { } p && fetchLocal is { } fs && fs.Format == "KQL")
            {
                var template = Str(fs.Skill["Settings"]?["Template"]);
                var target = Str(fs.Skill["Settings"]?["Target"]);
                var cols = KqlChecker.Check(template, fs.Path, target).ResultColumns;
                if (cols.Count > 0 && p.Skill["Inputs"] is JsonArray pin)
                    foreach (var inp in pin.OfType<JsonObject>())
                    {
                        var iname = Str(inp["Name"]);
                        var required = Str(inp["Required"]).Equals("true", StringComparison.OrdinalIgnoreCase);
                        if (required && !cols.Contains(iname, StringComparer.Ordinal))
                            f.Add(new(Severity.Error, tp + ".FetchSkill",
                                $"the query returns [{string.Join(", ", cols)}] but ProcessSkill needs an input named '{iname}'; project a column with that name."));
                    }
            }
        }
    }

    private static bool IsOwn(string reference, string descriptorName) =>
        descriptorName.Length > 0 && reference.StartsWith(descriptorName + ".", StringComparison.Ordinal);

    private static (JsonObject Skill, string Format, string Path)? Resolve(string reference, string descriptorName,
        Dictionary<string, (JsonObject Skill, string Format, string Path)> skills)
    {
        if (!IsOwn(reference, descriptorName)) return null;
        var skillName = reference[(descriptorName.Length + 1)..];
        return skills.TryGetValue(skillName, out var s) ? s : null;
    }

    private static string Str(JsonNode? n) => n is JsonValue v && v.TryGetValue<string>(out var s) ? s ?? "" : "";
}
