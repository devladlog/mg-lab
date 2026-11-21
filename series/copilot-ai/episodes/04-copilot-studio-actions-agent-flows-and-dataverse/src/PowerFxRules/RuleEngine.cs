using System.Globalization;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Contoso.VendorDesk;

/// <summary>
/// Evaluates the Power Fx formulas in rules/*.fx with the open-source Power Fx interpreter.
/// A Copilot Studio topic variable is addressed as <c>Topic.Name</c>; here <c>Topic</c> is a record.
/// </summary>
public sealed class RuleEngine
{
    private readonly string _rulesDir;

    public RuleEngine(string? rulesDir = null)
    {
        _rulesDir = rulesDir ?? Path.Combine(AppContext.BaseDirectory, "rules");
    }

    public string Formula(string ruleName) => File.ReadAllText(Path.Combine(_rulesDir, ruleName + ".fx"));

    public FormulaValue Evaluate(string ruleName, IReadOnlyDictionary<string, object?> topic)
    {
        // Copilot Studio formulas use US-style numbers (Learn: "Create expressions using Power Fx").
        var engine = new RecalcEngine();
        var fields = topic.Select(kv => new NamedValue(kv.Key, ToValue(kv.Value))).ToArray();
        var record = FormulaValue.NewRecordFromFields(fields);
        engine.UpdateVariable("Topic", record);

        FormulaValue result;
        try
        {
            result = engine.Eval(Formula(ruleName), options: new ParserOptions { Culture = CultureInfo.GetCultureInfo("en-US") });
        }
        catch (Exception e)   // compile errors surface as AggregateException(InvalidOperationException(...))
        {
            var inner = e is AggregateException a ? a.GetBaseException() : e;
            throw new InvalidOperationException($"{ruleName}: {inner.Message}", inner);
        }
        if (result is ErrorValue err)
            throw new InvalidOperationException($"{ruleName}: " + string.Join("; ", err.Errors.Select(e => e.Message)));
        return result;
    }

    public string EvaluateText(string ruleName, IReadOnlyDictionary<string, object?> topic)
    {
        var v = Evaluate(ruleName, topic);
        return v is StringValue s ? s.Value : throw new InvalidOperationException($"{ruleName} returned {v.GetType().Name}, not text");
    }

    private static FormulaValue ToValue(object? o) => o switch
    {
        null => FormulaValue.NewBlank(),
        string s => FormulaValue.New(s),
        int i => FormulaValue.New((double)i),
        long l => FormulaValue.New((double)l),
        double d => FormulaValue.New(d),
        decimal m => FormulaValue.New((double)m),
        bool b => FormulaValue.New(b),
        _ => throw new ArgumentException($"Unsupported topic value type {o.GetType().Name}")
    };
}
