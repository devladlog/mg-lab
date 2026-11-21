using Kusto.Language;
using Kusto.Language.Symbols;
using Kusto.Language.Syntax;

namespace Contoso.SecCopilotKit;

public sealed record KqlResult(IReadOnlyList<Finding> Findings, IReadOnlyList<string> ResultColumns, bool SchemaChecked);

/// <summary>
/// Parses and analyses a KQL skill template with the Kusto.Language parser (the library the Kusto tools use) against the
/// advanced hunting tables of <see cref="HuntingSchema"/>.
/// </summary>
public static class KqlChecker
{
    public const int MaxTemplateChars = 80_000; // Learn: Template supports up to 80,000 chars

    public static KqlResult Check(string template, string path, string target = "Defender")
    {
        var findings = new List<Finding>();
        if (template.Length > MaxTemplateChars)
            findings.Add(new(Severity.Error, path, $"template has {template.Length} characters, the limit is {MaxTemplateChars}."));

        // 1. Replace placeholders with a sentinel, so the text parses like the query the service will run.
        var names = TemplateRenderer.Placeholders(template);
        var probe = TemplateRenderer.Render(template, names.ToDictionary(n => n, n => "SENTINEL_" + n), escape: false);

        // 2. Renamed tables: Learn says old queries are migrated automatically, so warn and analyse with the new name.
        foreach (var (oldName, newName) in HuntingSchema.RenamedTables)
        {
            if (probe.Contains(oldName, StringComparison.Ordinal))
            {
                findings.Add(new(Severity.Warning, path, $"table {oldName} was replaced by {newName} on 19 October 2026 (Learn); use {newName}."));
                probe = probe.Replace(oldName, newName, StringComparison.Ordinal);
            }
        }

        // 3. Placeholders must be inside a string literal.
        var syntaxOnly = KustoCode.Parse(probe);
        foreach (var token in syntaxOnly.GetLexicalTokens())
        {
            if (token.Text.Contains("SENTINEL_", StringComparison.Ordinal) && token.Kind != SyntaxKind.StringLiteralToken)
                findings.Add(new(Severity.Error, path, $"a placeholder is outside a string literal ('{token.Text}'); put it inside quotes so an input cannot add query operators."));
        }

        // 4. Syntax and, for Defender, columns.
        var schemaChecked = string.Equals(target, "Defender", StringComparison.OrdinalIgnoreCase);
        var code = schemaChecked ? KustoCode.ParseAndAnalyze(probe, HuntingSchema.Globals) : syntaxOnly;
        foreach (var d in code.GetDiagnostics())
        {
            var sev = d.Severity switch { "Error" => Severity.Error, "Warning" => Severity.Warning, _ => Severity.Info };
            if (sev == Severity.Info) continue;
            findings.Add(new(sev, path, $"KQL: {d.Message} (at offset {d.Start})"));
        }
        if (!schemaChecked)
            findings.Add(new(Severity.Info, path, $"target {target}: syntax checked only, its tables are not part of this kit's schema."));

        // 5. Hygiene: bounded and time-bound.
        var root = code.Syntax;
        bool bounded = root.GetDescendants<TakeOperator>().Count > 0 || root.GetDescendants<TopOperator>().Count > 0 ||
                       root.GetDescendants<SummarizeOperator>().Count > 0 || root.GetDescendants<CountOperator>().Count > 0;
        if (!bounded)
            findings.Add(new(Severity.Warning, path, "no take, top, summarize or count: the result is not bounded; the skill output goes to the model."));
        bool timeBound = root.GetDescendants<FilterOperator>().Any(w =>
            (w.Condition.ToString().Contains("Timestamp") || w.Condition.ToString().Contains("TimeGenerated")) &&
            (w.Condition.ToString().Contains("ago(") || w.Condition.ToString().Contains("between") || w.Condition.ToString().Contains("datetime(")));
        if (!timeBound)
            findings.Add(new(Severity.Warning, path, "no time filter on Timestamp: add 'where Timestamp > ago(7d)' to keep the query fast."));

        var columns = new List<string>();
        if (schemaChecked && code.ResultType is TableSymbol ts) columns.AddRange(ts.Columns.Select(c => c.Name));
        return new KqlResult(findings, columns, schemaChecked);
    }
}
