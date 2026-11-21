using System.Globalization;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Core.Utils;
using Microsoft.PowerFx.Types;

namespace ContosoInspections.Agent.Tests;

/// <summary>
/// Runs the episode 13 formulas on Microsoft's open-source Power Fx interpreter. Stubs (the engine has none of these): Notify, Back, Refresh and
/// the Microsoft Copilot Studio connector call, which the harness rewrites from MicrosoftCopilotStudio.ExecuteCopilotAsyncV2( to a function
/// that records the agent name and message and returns the answer the test set up (a test double, NOT agent output). Parent/Self are not
/// used by these files. The shape of the real connector call in Power Fx is unverified in Studio: see README.
/// </summary>
public sealed class Harness
{
    public CanvasSource App { get; }
    public RecalcEngine Engine { get; }
    public List<string> Calls { get; } = new();
    public List<(string Agent, string Message)> AgentCalls { get; } = new();
    public string? AgentAnswer { get; set; } = "";
    public string? AgentError { get; set; }
    public DefinitionsCheckResult FunctionsResult { get; }
    private static readonly ParserOptions Behavior = new() { AllowsSideEffects = true };

    public Harness(CanvasSource app)
    {
        App = app;
        var config = new PowerFxConfig();
        var symbols = new SymbolTable();
        config.SymbolTable = symbols;
        config.EnableSetFunction();
        config.AddFunction(new NotifyFunction(Calls));
        config.AddFunction(new BackFunction(Calls));
        var agent = new AgentFunction(this);
        config.AddFunction(agent);
        config.AddFunction(new RefreshFunction(Calls));
        Engine = new RecalcEngine(config);
        Enum("NotificationType", "Success", "Error", "Warning", "Information");
        Enum("DisplayMode", "Edit", "View", "Disabled");
        Enum("TextRole", "Default", "Heading1");
        Enum("TextMode", "SingleLine", "MultiLine");
        Enum("Live", "Off", "Polite", "Assertive");
        Engine.UpdateVariable("agentBusy", FormulaValue.New(false));
        Engine.UpdateVariable("agentReply", FormulaValue.New(""));
        Engine.UpdateVariable("selectedInspection", Inspection("INS-00003", "CWN-01"));
        Engine.UpdateVariable("txtAsk", FormulaValue.NewRecordFromFields(new NamedValue("Text", FormulaValue.New("Which items are still open?"))));
        Recalc();
        var udfs = string.Join("\n", App.Definitions().Where(d => d.Kind != CanvasSource.DefinitionKind.NamedFormula).Select(d => d.Text + ";"));
        FunctionsResult = Engine.AddUserDefinedFunction(udfs, CultureInfo.InvariantCulture, Engine.EngineSymbols, allowSideEffects: true);
    }

    /// <summary>Only the columns the app reads, with the display names Dataverse gives them.</summary>
    public static RecordValue Inspection(string number, string siteCode)
    {
        var site = RecordType.Empty().Add("cin_sitecode", FormulaType.String, "Site code");
        var rt = RecordType.Empty().Add("cin_name", FormulaType.String, "Inspection number").Add("cin_siteid", site, "Site");
        return FormulaValue.NewRecordFromFields(rt, new NamedValue("cin_name", FormulaValue.New(number)),
            new NamedValue("cin_siteid", FormulaValue.NewRecordFromFields(site, new NamedValue("cin_sitecode", FormulaValue.New(siteCode)))));
    }

    public void SetVariable(string name, FormulaValue v) => Engine.UpdateVariable(name, v);
    public void Recalc()
    {
        foreach (var d in App.Definitions().Where(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula))
            Engine.UpdateVariable(d.Name, Eval(d.Expression));
    }

    public static string Rewrite(string f) => f.Replace("MicrosoftCopilotStudio.ExecuteCopilotAsyncV2(", "MCSExecute(").Replace("Refresh('Inspection items')", "RefreshItems()");
    public FormulaValue Eval(string formula)
    {
        var r = Engine.EvalAsync(Rewrite(formula), CancellationToken.None, Behavior).GetAwaiter().GetResult();
        return r is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : r;
    }
    public string Text(string formula) => Eval(formula) switch { StringValue s => s.Value, BlankValue or VoidValue => "", var v => v.ToObject()?.ToString() ?? "" };
    public bool Bool(string formula) => ((BooleanValue)Eval(formula)).Value;
    public string Run(string control, string property) => Text(App.Formula(control, property));

    private void Enum(string name, params string[] members) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(members.Select(m => new NamedValue(m, FormulaValue.New(m)))));

    private sealed class NotifyFunction(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message, StringValue type) { calls.Add($"Notify({type.Value}): {message.Value}"); return FormulaValue.New(true); }
    }

    private sealed class RefreshFunction(List<string> calls) : ReflectionFunction("RefreshItems", FormulaType.Boolean)
    {
        public BooleanValue Execute() { calls.Add("Refresh(Inspection items)"); return FormulaValue.New(true); }
    }

    private sealed class BackFunction(List<string> calls) : ReflectionFunction("Back", FormulaType.Boolean)
    {
        public BooleanValue Execute() { calls.Add("Back()"); return FormulaValue.New(true); }
    }

    private sealed class AgentFunction(Harness h) : ReflectionFunction("MCSExecute", RecordType.Empty().Add("lastResponse", FormulaType.String),
        FormulaType.String, RecordType.Empty().Add("message", FormulaType.String))
    {
        public RecordValue Execute(StringValue agent, RecordValue args)
        {
            h.AgentCalls.Add((agent.Value, ((StringValue)args.GetField("message")).Value));
            if (h.AgentError is { } err) return FormulaValue.NewRecordFromFields(new NamedValue("lastResponse", FormulaValue.NewError(new ExpressionError { Message = err, Kind = ErrorKind.Network })));
            return FormulaValue.NewRecordFromFields(new NamedValue("lastResponse", FormulaValue.New(h.AgentAnswer ?? "")));
        }
    }
}
