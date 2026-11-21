using System.Text;
using System.Text.RegularExpressions;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace PowerFxReview;

public enum Severity { Error, Warning, Info }

public sealed record Finding(string Code, Severity Severity, string Message);

public sealed record FormulaReview(FormulaItem Item, string Status, string? ReturnType, IReadOnlyList<Finding> Findings)
{
    public bool HasErrors => Findings.Any(f => f.Severity == Severity.Error);
}

/// <summary>
/// Reviews formulas the way you should review anything Copilot wrote for you: first with the real Power Fx
/// parser and type checker (the open source engine Power Apps is built on), then with a few extra rules.
/// It does not replace Power Apps Studio: functions that only exist in the host (Navigate, Patch, Set ...)
/// are recognised but not checked, and delegation warnings come from Studio only.
/// </summary>
public sealed class Reviewer
{
    // Functions the standalone engine knows by name but does not run ("recognized but not supported").
    // They need the Power Apps host, so a formula that uses one is only partly checked.
    static readonly HashSet<string> HostFunctions = new(StringComparer.Ordinal)
    {
        "Navigate", "Back", "Notify", "Set", "UpdateContext", "Defaults", "Patch", "Collect", "ClearCollect", "Clear",
        "Remove", "RemoveIf", "Update", "UpdateIf", "SubmitForm", "ResetForm", "NewForm", "EditForm", "ViewForm",
        "Refresh", "Launch", "Exit", "Param", "SaveData", "LoadData", "Errors", "Revert", "Select", "SetFocus", "Reset",
    };

    // Learn, "Query limitations: Delegation and query limits": nondelegable functions listed there, plus Mid and Len
    // from its worked example. If a formula that queries a data source uses one, Studio shows a delegation warning
    // and Power Apps works on the first 500 rows (limit can be raised to 10,000).
    static readonly HashSet<string> NonDelegable = new(StringComparer.Ordinal)
    {
        "FirstN", "Last", "LastN", "Choices", "Concat", "Collect", "ClearCollect", "GroupBy", "Ungroup", "Mid", "Len",
    };

    // Calls that change data and can fail.
    static readonly HashSet<string> DataChanging = new(StringComparer.Ordinal)
    {
        "Patch", "Remove", "RemoveIf", "Update", "UpdateIf", "SubmitForm",
    };

    static readonly Regex Call = new(@"(?<![\w.])([A-Za-z_]\w*)\s*\(", RegexOptions.Compiled);
    static readonly Regex Connector = new(@"(?<![\w.])([A-Za-z_]\w*\.[A-Za-z_]\w*)\s*\(", RegexOptions.Compiled);
    static readonly Regex Declared = new(@"\b(Set|Collect|ClearCollect)\s*\(\s*(\w+)", RegexOptions.Compiled);
    static readonly Regex Email = new(@"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}", RegexOptions.Compiled);
    static readonly Regex Guid = new(@"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", RegexOptions.Compiled);

    readonly ReviewContext _ctx;
    readonly RecalcEngine _engine = new();
    readonly RecordType _scope;

    public Reviewer(ReviewContext ctx, IEnumerable<string> screens)
    {
        _ctx = ctx;
        _scope = ctx.ToRecordType(screens);
    }

    public FormulaReview Review(FormulaItem item)
    {
        var findings = new List<Finding>();
        var formula = item.Formula;
        var code = StripStrings(formula);
        var calls = Call.Matches(code).Select(m => m.Groups[1].Value).ToList();
        var hostCalls = calls.Where(HostFunctions.Contains).Distinct().ToList();
        // Connector calls such as Office365Outlook.SendEmailV2(...) also need the host.
        hostCalls.AddRange(Connector.Matches(code).Select(m => m.Groups[1].Value).Distinct());
        var declared = Declared.Matches(code).Select(m => m.Groups[2].Value).ToHashSet();

        var options = new ParserOptions { AllowsSideEffects = item.IsBehavior };
        var check = _engine.Check(formula, _scope, options);

        // The standalone engine wants && between predicates; Learn says Filter in canvas apps accepts several
        // formulas and combines them with And. That is an engine difference, not a mistake in the formula.
        bool multiPredicate = !check.IsSuccess && check.Errors.Any(e => e.Message.Contains("combine multiple predicates", StringComparison.Ordinal));

        string status;
        string? returnType = null;
        if (check.IsSuccess)
        {
            status = "ok";
            returnType = Describe(check.ReturnType);
            CheckReturnType(item, check.ReturnType, findings);
        }
        else if (hostCalls.Count > 0 || multiPredicate)
        {
            // Keep what the engine can still tell us for sure: syntax errors and names that do not exist.
            status = "partial";
            foreach (var e in check.Errors)
            {
                if (e.Message.Contains("recognized but not supported")) continue;
                // Set(x, ...) and Collect(x, ...) create x: that is a declaration, not an unknown name.
                if (declared.Contains(e.Span.GetFragment(formula))) continue;
                if (e.Message.StartsWith("Name isn't valid", StringComparison.Ordinal) || !check.Parse.IsSuccess)
                    findings.Add(new Finding("PF001", Severity.Error, $"{e.Message} [{e.Span.GetFragment(formula)}]"));
            }
            if (hostCalls.Count > 0)
                findings.Add(new Finding("PF006", Severity.Info,
                    $"Uses {string.Join(", ", hostCalls)}: needs the Power Apps host, so only syntax and names were checked (names created by Set or Collect are not typed here). Studio is the final check."));
            if (multiPredicate)
                findings.Add(new Finding("PF007", Severity.Info,
                    "Filter with several predicates: canvas apps accept it (Learn: the formulas are combined with And), this engine wants && . Only syntax and names were checked."));
        }
        else
        {
            status = "error";
            foreach (var e in check.Errors)
                findings.Add(new Finding("PF001", Severity.Error, $"{e.Message} [{e.Span.GetFragment(formula)}]"));
        }

        HardCodedValues(formula, findings);
        Delegation(code, calls, findings);
        ErrorHandling(item, code, calls, findings);

        if (findings.Any(f => f.Severity == Severity.Error)) status = "error";
        return new FormulaReview(item, status, returnType, findings);
    }

    void CheckReturnType(FormulaItem item, FormulaType type, List<Finding> findings)
    {
        switch (item.Property)
        {
            case "Text" when type is TableType or RecordType:
                findings.Add(new Finding("PF002", Severity.Error, $"{item.Property} expects text but the formula returns {Describe(type)}."));
                break;
            case "Visible" or "Required" when type != FormulaType.Boolean && type != FormulaType.Blank:
                findings.Add(new Finding("PF002", Severity.Warning, $"{item.Property} expects true or false but the formula returns {Describe(type)}."));
                break;
            case "Items" when type is not TableType && type != FormulaType.Blank:
                findings.Add(new Finding("PF002", Severity.Error, $"Items expects a table but the formula returns {Describe(type)}."));
                break;
        }
    }

    static void HardCodedValues(string formula, List<Finding> findings)
    {
        foreach (var literal in StringLiterals(formula))
        {
            if (Email.IsMatch(literal))
                findings.Add(new Finding("PF003", Severity.Warning, $"Hard-coded e-mail address \"{literal}\": move it to a table column, an environment variable or a setting."));
            if (Guid.IsMatch(literal))
                findings.Add(new Finding("PF003", Severity.Warning, $"Hard-coded GUID \"{literal}\": it will not survive a move to another environment."));
        }
    }

    void Delegation(string code, List<string> calls, List<Finding> findings)
    {
        var sources = _ctx.Tables.Where(t => t.Value.DataSource).Select(t => t.Key)
            .Where(name => Regex.IsMatch(code, $@"(?<![\w.]){Regex.Escape(name)}(?![\w])")).ToList();
        if (sources.Count == 0) return;
        var bad = calls.Where(NonDelegable.Contains).Distinct().ToList();
        if (bad.Count > 0)
            findings.Add(new Finding("PF004", Severity.Warning,
                $"{string.Join(", ", bad)} cannot be delegated ({string.Join(", ", sources)} is a data source): Power Apps only reads the first 500 rows (up to 10,000 if you raise the limit). Studio's yellow triangle is the authority."));
    }

    void ErrorHandling(FormulaItem item, string code, List<string> calls, List<Finding> findings)
    {
        if (!item.IsBehavior) return;
        var changing = calls.Where(DataChanging.Contains).Distinct().ToList();
        // Collect / ClearCollect only count when they write to a data source.
        foreach (var name in new[] { "Collect", "ClearCollect" })
            foreach (var table in _ctx.Tables.Where(t => t.Value.DataSource).Select(t => t.Key))
                if (Regex.IsMatch(code, $@"\b{name}\s*\(\s*{Regex.Escape(table)}\b")) changing.Add(name);
        if (changing.Count == 0) return;
        bool handled = calls.Contains("IfError") || calls.Contains("Errors") || calls.Contains("IsError");
        if (!handled)
            findings.Add(new Finding("PF005", Severity.Warning,
                $"{string.Join(", ", changing.Distinct())} can fail and nothing handles the error: wrap it in IfError (and tell the user with Notify)."));
    }

    static string Describe(FormulaType t) => t switch
    {
        TableType => "a table",
        RecordType => "a record",
        _ when t == FormulaType.String => "text",
        _ when t == FormulaType.Number => "a number",
        _ when t == FormulaType.Boolean => "a boolean",
        _ when t == FormulaType.Date => "a date",
        _ when t == FormulaType.DateTime => "a date and time",
        _ => t.ToString() ?? "unknown",
    };

    /// <summary>Replaces the content of "text" literals so regexes only see code.</summary>
    internal static string StripStrings(string formula)
    {
        var sb = new StringBuilder();
        bool inStr = false;
        for (int i = 0; i < formula.Length; i++)
        {
            char c = formula[i];
            if (c == '"')
            {
                if (inStr && i + 1 < formula.Length && formula[i + 1] == '"') { i++; continue; } // "" escape
                inStr = !inStr;
                sb.Append('"');
            }
            else if (!inStr) sb.Append(c);
        }
        return sb.ToString();
    }

    internal static IEnumerable<string> StringLiterals(string formula)
    {
        var sb = new StringBuilder();
        bool inStr = false;
        for (int i = 0; i < formula.Length; i++)
        {
            char c = formula[i];
            if (c == '"')
            {
                if (inStr && i + 1 < formula.Length && formula[i + 1] == '"') { sb.Append('"'); i++; continue; }
                if (inStr) { yield return sb.ToString(); sb.Clear(); }
                inStr = !inStr;
            }
            else if (inStr) sb.Append(c);
        }
    }
}
