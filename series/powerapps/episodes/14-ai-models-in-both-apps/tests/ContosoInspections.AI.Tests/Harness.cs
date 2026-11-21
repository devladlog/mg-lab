using Microsoft.PowerFx.Core;
using System.Globalization;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Core.Utils;
using Microsoft.PowerFx.Types;

namespace ContosoInspections.AI.Tests;

/// <summary>
/// Runs the episode 14 formulas on Microsoft's open-source Power Fx interpreter. The engine has no connectors, so the harness rewrites the
/// four model calls to recording test doubles: 'InspectionTriage'.Predict( -> AIBPredict(, ContosoFoundryTriage.TriageFinding( -> FoundryCall(,
/// ClaudeTriage.Run( -> ClaudeRun(, and Patch('Inspection items', -> PatchItem(. A double returns the text the TEST set up. It is NOT model output,
/// and no accuracy claim anywhere in this episode comes from it. The real call shapes are unverified in Studio: see README.
/// </summary>
public sealed class Harness
{
    public CanvasSource App { get; }
    public RecalcEngine Engine { get; }
    public List<string> Calls { get; } = new();
    public List<string> PredictInputs { get; } = new();
    public List<(string Model, string System, string User)> FoundryCalls { get; } = new();
    public List<(string Notes, string Photo, string Model)> ClaudeCalls { get; } = new();
    public List<Dictionary<string, string>> Patches { get; } = new();
    public string Answer { get; set; } = "";
    public string? Error { get; set; }
    public string PhotoJsonValue { get; set; } = "null";
    public DefinitionsCheckResult FunctionsResult { get; }
    private static readonly ParserOptions Behavior = new() { AllowsSideEffects = true };

    private readonly string _itemVar;
    private readonly HashSet<string> _skip;

    public Harness(CanvasSource app, string itemVar = "selectedItem", params string[] skipNamedFormulas)
    {
        App = app;
        _itemVar = itemVar;
        _skip = skipNamedFormulas.ToHashSet();
        var config = new PowerFxConfig();
        config.SymbolTable = new SymbolTable();
        config.EnableSetFunction();
        config.EnableJsonFunctions();
        config.AddFunction(new NotifyFunction(Calls));
        config.AddFunction(new BackFunction(Calls));
        config.AddFunction(new PredictFunction(this));
        config.AddFunction(new FoundryFunction(this));
        config.AddFunction(new ClaudeFunction(this));
        config.AddFunction(new PatchFunction(this));
        config.AddFunction(new PhotoJsonFunction(this));
        Engine = new RecalcEngine(config);
        Enum("NotificationType", "Success", "Error", "Warning", "Information");
        Enum("DisplayMode", "Edit", "View", "Disabled");
        Enum("TextRole", "Default", "Heading1");
        Enum("TextMode", "SingleLine", "MultiLine");
        Enum("Live", "Off", "Polite", "Assertive");
        Enum("AI severity (Inspection items)", "Info", "Minor", "Major", "Critical");
        Engine.UpdateVariable("triageBusy", FormulaValue.New(false));
        Engine.UpdateVariable("triageRaw", FormulaValue.New(""));
        Engine.UpdateVariable("triageRoute", FormulaValue.New("foundry"));
        SetItem("Fire door wedged open with an extinguisher in the east stairwell.", "");
        SetNotes("Fire door wedged open with an extinguisher in the east stairwell.");
        Recalc();
        var udfs = string.Join("\n", App.Definitions().Where(d => d.Kind != CanvasSource.DefinitionKind.NamedFormula).Select(d => d.Text + ";"));
        FunctionsResult = Engine.AddUserDefinedFunction(udfs, CultureInfo.InvariantCulture, Engine.EngineSymbols, allowSideEffects: true);
    }

    public void SetItem(string notes, string photo) =>
        Engine.UpdateVariable(_itemVar, FormulaValue.NewRecordFromFields(
            new NamedValue("Notes", FormulaValue.New(notes)), new NamedValue("Photo", FormulaValue.New(photo))));
    public void SetNotes(string text) =>
        Engine.UpdateVariable("txtTriageNotes", FormulaValue.NewRecordFromFields(new NamedValue("Text", FormulaValue.New(text))));
    public void SetVariable(string name, FormulaValue v) => Engine.UpdateVariable(name, v);
    public void Recalc()
    {
        foreach (var d in App.Definitions().Where(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula && !_skip.Contains(d.Name)))
            Engine.UpdateVariable(d.Name, Eval(d.Expression));
    }

    public static string Rewrite(string f) => System.Text.RegularExpressions.Regex.Replace(f, @"Patch\(\s*'Inspection items',", "PatchItem(")
        .Replace("'InspectionTriage'.Predict(", "AIBPredict(")
        .Replace("ContosoFoundryTriage.TriageFinding(", "FoundryCall(")
        .Replace("ClaudeTriage.Run(", "ClaudeRun(")
        .Replace("JSON(selectedItem.Photo, JSONFormat.IncludeBinaryData)", "PhotoJson()").Replace("JSON(ThisInspectionItem.Photo, JSONFormat.IncludeBinaryData)", "PhotoJson()")
        ;

    public FormulaValue Eval(string formula)
    {
        var r = Engine.EvalAsync(Rewrite(formula), CancellationToken.None, Behavior).GetAwaiter().GetResult();
        return r is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : r;
    }
    public string Text(string formula) => Eval(formula) switch { StringValue s => s.Value, BlankValue or VoidValue => "", var v => v.ToObject()?.ToString() ?? "" };
    public bool Bool(string formula) => ((BooleanValue)Eval(formula)).Value;
    public double Num(string formula) => ((NumberValue)Eval(formula)).Value;
    public string Run(string control, string property) => Text(App.Formula(control, property));

    private void Enum(string name, params string[] members) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(members.Select(m => new NamedValue(m, FormulaValue.New(m)))));

    private FormulaValue Fail() => FormulaValue.NewError(new ExpressionError { Message = Error!, Kind = ErrorKind.Network });

    private sealed class NotifyFunction(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message, StringValue type) { calls.Add($"Notify({type.Value}): {message.Value}"); return FormulaValue.New(true); }
    }

    private sealed class BackFunction(List<string> calls) : ReflectionFunction("Back", FormulaType.Boolean)
    {
        public BooleanValue Execute() { calls.Add("Back()"); return FormulaValue.New(true); }
    }

    private sealed class PhotoJsonFunction(Harness h) : ReflectionFunction("PhotoJson", FormulaType.String)
    {
        public StringValue Execute() => FormulaValue.New(h.PhotoJsonValue);
    }

    private sealed class PredictFunction(Harness h) : ReflectionFunction("AIBPredict", RecordType.Empty().Add("text", FormulaType.String), FormulaType.String)
    {
        public FormulaValue Execute(StringValue input)
        {
            h.PredictInputs.Add(input.Value);
            if (h.Error != null) return FormulaValue.NewRecordFromFields(new NamedValue("text", h.Fail()));
            return FormulaValue.NewRecordFromFields(new NamedValue("text", FormulaValue.New(h.Answer)));
        }
    }

    private sealed class ClaudeFunction(Harness h) : ReflectionFunction("ClaudeRun", RecordType.Empty().Add("text", FormulaType.String),
        FormulaType.String, FormulaType.String, FormulaType.String)
    {
        public FormulaValue Execute(StringValue notes, StringValue photo, StringValue model)
        {
            h.ClaudeCalls.Add((notes.Value, photo.Value, model.Value));
            if (h.Error != null) return FormulaValue.NewRecordFromFields(new NamedValue("text", h.Fail()));
            return FormulaValue.NewRecordFromFields(new NamedValue("text", FormulaValue.New(h.Answer)));
        }
    }

    private static readonly RecordType Message = RecordType.Empty().Add("content", FormulaType.String);
    private static readonly RecordType Choice = RecordType.Empty().Add("message", Message);
    private static readonly RecordType FoundryResult = RecordType.Empty().Add("choices", TableType.Empty().Add("message", Message));

    private sealed class FoundryFunction(Harness h) : ReflectionFunction("FoundryCall", FoundryResult, RecordType.Empty().Add("model", FormulaType.String).Add("max_tokens", FormulaType.Number).Add("messages", TableType.Empty().Add("role", FormulaType.String).Add("content", FormulaType.String)))
    {
        public FormulaValue Execute(RecordValue args)
        {
            var rows = ((TableValue)args.GetField("messages")).Rows.Select(r => ((StringValue)r.Value.GetField("content")).Value).ToList();
            h.FoundryCalls.Add((((StringValue)args.GetField("model")).Value, rows[0], rows[1]));
            if (h.Error != null) return h.Fail();
            var msg = FormulaValue.NewRecordFromFields(Message, new NamedValue("content", FormulaValue.New(h.Answer)));
            var choice = FormulaValue.NewRecordFromFields(Choice, new NamedValue("message", msg));
            return FormulaValue.NewRecordFromFields(FoundryResult, new NamedValue("choices", FormulaValue.NewTable(Choice, choice)));
        }
    }

    private sealed class PatchFunction(Harness h) : ReflectionFunction("PatchItem", FormulaType.Boolean, RecordType.Empty(), RecordType.Empty())
    {
        public BooleanValue Execute(RecordValue item, RecordValue changes)
        {
            h.Patches.Add(changes.Fields.ToDictionary(f => f.Name, f => f.Value.ToObject()?.ToString() ?? ""));
            return FormulaValue.New(true);
        }
    }
}
