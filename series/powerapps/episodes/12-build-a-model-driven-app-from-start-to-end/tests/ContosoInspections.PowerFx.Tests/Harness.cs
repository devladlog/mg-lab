using System.Globalization;
using System.Text.Json.Nodes;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Core;
using Microsoft.PowerFx.Core.Utils;
using Microsoft.PowerFx.Types;

namespace ContosoInspections.PowerFx.Tests;

/// <summary>
/// Runs the command bar formulas and the custom page formulas on Microsoft's open-source Power Fx interpreter, against in-memory
/// tables built FROM THE SCHEMA FILE (same logical names, display names and local choices as Dataverse gives a canvas app or a
/// command) and filled from the seed CSVs. The pieces the host provides are stubs that record their calls: Self.Selected (commands),
/// Param (custom pages), Notify, Confirm and Navigate. This tests formula LOGIC. It can't test delegation, permissions or how the
/// real command designer or Studio treats a formula.
/// </summary>
public sealed class Harness
{
    public RecalcEngine Engine { get; }
    public Dictionary<string, RecordType> Types { get; } = new();
    public Dictionary<string, OptionSet> Choices { get; } = new();           // key: "Status (Inspections)"
    public List<string> Calls { get; } = new();
    public bool ConfirmAnswer { get; set; } = true;
    public Dictionary<string, string> Params { get; } = new();
    private readonly Dictionary<string, string> plural = new();              // logical table name -> plural display name
    private readonly Dictionary<string, TableValue> tables = new();         // by logical name
    private static readonly ParserOptions Behavior = new() { AllowsSideEffects = true };

    public Harness()
    {
        var config = new PowerFxConfig();
        var symbols = new SymbolTable();
        symbols.EnableMutationFunctions();
        config.SymbolTable = symbols;
        config.EnableSetFunction();

        // Types in dependency order: a lookup column is a record of the target table's type.
        foreach (var t in InDependencyOrder(Episode.Schema["tables"]!.AsArray()))
        {
            var logical = t!["logicalName"]!.GetValue<string>();
            var pl = t["pluralName"]!.GetValue<string>();
            plural[logical] = pl;
            var rt = RecordType.Empty().Add($"{logical}id", FormulaType.Guid, t["displayName"]!.GetValue<string>())
                .Add(t["primaryName"]!["logicalName"]!.GetValue<string>(), FormulaType.String, t["primaryName"]!["displayName"]!.GetValue<string>());
            foreach (var c in t["columns"]!.AsArray())
            {
                var name = c!["logicalName"]!.GetValue<string>();
                var disp = c["displayName"]!.GetValue<string>();
                FormulaType ft;
                switch (c["type"]!.GetValue<string>())
                {
                    case "string" or "email" or "phone" or "memo": ft = FormulaType.String; break;
                    case "whole": ft = FormulaType.Decimal; break;
                    case "bool": ft = FormulaType.Boolean; break;
                    case "date": ft = FormulaType.Date; break;
                    case "lookup": ft = Types[c["target"]!.GetValue<string>()]; break;
                    case "choice":
                        // Dataverse local choices appear as 'Column (Table plural)', e.g. 'Status (Inspections)'.
                        var optName = $"{disp} ({pl})";
                        var os = new OptionSet(optName, DisplayNameUtility.MakeUnique(c["options"]!.AsArray().ToDictionary(o => Identifier(o![0]!.GetValue<string>()), o => o![0]!.GetValue<string>())));
                        config.AddOptionSet(os);
                        Choices[optName] = os;
                        ft = os.FormulaType; break;
                    default: throw new NotSupportedException(c["type"]!.ToString());
                }
                rt = rt.Add(name, ft, disp);
            }
            Types[logical] = rt;
            
        }

        config.AddFunction(new NotifyOne(Calls));
        config.AddFunction(new NotifyTwo(Calls));
        config.AddFunction(new ConfirmFunction(Calls, () => ConfirmAnswer));
        config.AddFunction(new NavigateRecordPage(Calls));
        config.AddFunction(new ParamFunction(Params));

        Engine = new RecalcEngine(config);
        Enum("NotificationType", "Success", "Error", "Warning", "Information");   // Learn: Success isn't supported in commands (shown as informational)
        Enum("FormMode", "Edit", "New", "View");                                  // Self.Selected.State: Edit = 0, New = 1, View = 2
        Enum("FontWeight", "Normal", "Semibold", "Bold");
        Engine.UpdateVariable("Inspection review board", FormulaValue.New("Inspection review board"));

        // Seed data in dependency order, like the import order in demo.md.
        Fill("cin_inspector", Episode.Csv("inspectors.csv"));
        Fill("cin_site", Episode.Csv("sites.csv"));
        var inspections = Episode.Csv("inspections.csv");
        for (var i = 0; i < inspections.Count; i++) inspections[i]["Inspection number"] = $"INS-{1000 + i:D5}";   // what the autonumber gives
        Fill("cin_inspection", inspections);
        Fill("cin_inspectionitem", Episode.Csv("items.csv"));
    }

    // ------------------------------------------------------------------------------------------------ data
    /// <summary>The engine's live copy of the table (UpdateVariable copies it, and Patch finds rows by identity in that copy).</summary>
    public TableValue Table(string pluralName) => (TableValue)Engine.GetValue(pluralName);

    /// <summary>From now on every write to the table fails with this message (e.g. no Write privilege).</summary>
    public void MakeReadOnly(string pluralName, string message) => Engine.UpdateVariable(pluralName, new ReadOnlyTable(Table(pluralName), message));
    public TableValue Inspections => Table("Inspections");
    public TableValue Items => Table("Inspection items");

    private void Fill(string logical, List<Dictionary<string, string>> csv)
    {
        var t = Episode.Schema["tables"]!.AsArray().Single(x => x!["logicalName"]!.GetValue<string>() == logical)!;
        var rt = Types[logical];
        var records = new List<RecordValue>();
        for (var i = 0; i < csv.Count; i++)
        {
            var row = csv[i];
            var fields = new List<NamedValue>
            {
                new($"{logical}id", FormulaValue.New(new Guid(i + 1, (short)logical.Length, 0, [0, 0, 0, 0, 0, 0, 0, 1]))),
                new(t["primaryName"]!["logicalName"]!.GetValue<string>(), FormulaValue.New(row[t["primaryName"]!["displayName"]!.GetValue<string>()])),
            };
            foreach (var c in t["columns"]!.AsArray())
            {
                row.TryGetValue(c!["displayName"]!.GetValue<string>(), out var raw);
                fields.Add(new NamedValue(c["logicalName"]!.GetValue<string>(), Convert(logical, c, rt.GetFieldType(c["logicalName"]!.GetValue<string>()), raw)));
            }
            records.Add(FormulaValue.NewRecordFromFields(rt, fields));
        }
        var table = FormulaValue.NewTable(rt, records);
        tables[logical] = table;
        Engine.UpdateVariable(plural[logical], table);
    }

    private FormulaValue Convert(string table, JsonNode col, FormulaType type, string? raw)
    {
        if (string.IsNullOrEmpty(raw)) return FormulaValue.NewBlank(type);
        switch (col["type"]!.GetValue<string>())
        {
            case "whole": return FormulaValue.New(decimal.Parse(raw, CultureInfo.InvariantCulture));
            case "bool": return FormulaValue.New(raw == "Yes");
            case "date": return FormulaValue.NewDateOnly(DateTime.ParseExact(raw, "yyyy-MM-dd", CultureInfo.InvariantCulture));
            case "choice":
                var os = Choices[$"{col["displayName"]!.GetValue<string>()} ({plural[table]})"];
                return os.TryGetValue(new DName(Identifier(raw)), out var v) ? v : throw new ArgumentException($"{raw} is not an option of {os.EntityName}");
            case "lookup":
                var target = col["target"]!.GetValue<string>();
                var nameField = Episode.Schema["tables"]!.AsArray().Single(x => x!["logicalName"]!.GetValue<string>() == target)!["primaryName"]!["logicalName"]!.GetValue<string>();
                return tables[target].Rows.Select(r => r.Value).Single(r => ((StringValue)r.GetField(nameField)).Value == raw);
            default: return FormulaValue.New(raw);
        }
    }

    /// <summary>Opens the custom page for an inspection: Navigate(record, {Page: ...}) hands over its id, the page reads it with Param("id").</summary>
    public void LoadPage(PageSource page, string number)
    {
        Params["etn"] = "cin_inspection";
        Params["id"] = ((GuidValue)Inspection(number).GetField("cin_inspectionid")).Value.ToString();
        foreach (var (name, expression) in page.NamedFormulas()) Engine.SetFormula(name, Shim(expression), null);
    }

    public RecordValue Inspection(string number) =>
        Inspections.Rows.Select(r => r.Value).Single(r => ((StringValue)r.GetField("cin_name")).Value == number);

    /// <summary>Tables that are the target of a lookup must exist before the tables that point at them.</summary>
    private static List<JsonNode> InDependencyOrder(JsonArray tables)
    {
        var left = tables.Select(t => t!).ToList();
        var done = new List<JsonNode>();
        while (left.Count > 0)
        {
            var next = left.First(t => t["columns"]!.AsArray().Where(c => c!["type"]!.GetValue<string>() == "lookup")
                .All(c => done.Any(d => d["logicalName"]!.GetValue<string>() == c!["target"]!.GetValue<string>())));
            left.Remove(next); done.Add(next);
        }
        return done;
    }

    public static string Identifier(string label) => new string(label.Where(char.IsLetterOrDigit).ToArray());
    public static OptionSetValue Option(OptionSet set, string label) => set.TryGetValue(new DName(Identifier(label)), out var v) ? v : throw new ArgumentException(label);

    // ------------------------------------------------------------------------------------------------ Self.Selected (commands)
    /// <summary>The host's Self.Selected: Item is blank unless exactly one row is selected (Learn: Item is blank if SelectionMax &lt;> 1).</summary>
    public void SelectOne(string number, string state = "View") => SetSelected(Inspection(number), [Inspection(number)], state);

    public void SelectMany(params string[] numbers) => SetSelected(null, numbers.Select(Inspection).ToArray(), "View");

    public void SelectNothing() => SetSelected(null, [], "View");

    private void SetSelected(RecordValue? item, RecordValue[] all, string state)
    {
        var rt = Types["cin_inspection"];
        var selected = FormulaValue.NewRecordFromFields(
            new NamedValue("Item", item ?? (FormulaValue)FormulaValue.NewBlank(rt)),
            new NamedValue("AllItems", FormulaValue.NewTable(rt, all)),
            new NamedValue("State", FormulaValue.New(state)),
            new NamedValue("Unsaved", FormulaValue.New(false)));
        Engine.UpdateVariable("SelfHost", FormulaValue.NewRecordFromFields(new NamedValue("Selected", selected)));
    }

    // ------------------------------------------------------------------------------------------------ evaluation
    public FormulaValue Eval(string formula)
    {
        var result = Engine.EvalAsync(Shim(formula), CancellationToken.None, Behavior).GetAwaiter().GetResult();
        return result is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : result;
    }

    public CheckResult Check(string formula) => Engine.Check(Shim(formula), Behavior);

    /// <summary>"Self" is reserved by the Power Fx parser (it means "this control" in Studio), so the interpreter can't host a variable of that name. The host object is called SelfHost here and the formulas are rewritten before they run.</summary>
    private static string Shim(string formula) => System.Text.RegularExpressions.Regex.Replace(formula, @"\bSelf\.", "SelfHost.");

    public string Text(string formula) => Eval(formula) switch
    {
        StringValue s => s.Value,
        OptionSetValue o => o.DisplayName,
        BlankValue => "",
        var v => v.ToObject()?.ToString() ?? "",
    };

    public bool Bool(string formula) => ((BooleanValue)Eval(formula)).Value;

    public string Status(string number) => ((OptionSetValue)Inspection(number).GetField("cin_status")).DisplayName;

    private void Enum(string name, params string[] members) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(members.Select(m => new NamedValue(m, FormulaValue.New(m)))));

    // ------------------------------------------------------------------------------------------------ host stubs
    private sealed class NotifyOne(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message) { calls.Add($"Notify(Information): {message.Value}"); return FormulaValue.New(true); }
    }

    private sealed class NotifyTwo(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message, StringValue type) { calls.Add($"Notify({type.Value}): {message.Value}"); return FormulaValue.New(true); }
    }

    private static readonly RecordType ConfirmOptions = RecordType.Empty().Add("ConfirmButton", FormulaType.String).Add("CancelButton", FormulaType.String);

    private sealed class ConfirmFunction(List<string> calls, Func<bool> answer) : ReflectionFunction("Confirm", FormulaType.Boolean, FormulaType.String, ConfirmOptions)
    {
        public BooleanValue Execute(StringValue message, RecordValue options)
        {
            calls.Add($"Confirm: {message.Value} [{((StringValue)options.GetField("ConfirmButton")).Value}/{((StringValue)options.GetField("CancelButton")).Value}]");
            return FormulaValue.New(answer());
        }
    }

    private static readonly RecordType PageOption = RecordType.Empty().Add("Page", FormulaType.String);

    /// <summary>Navigate(record, {Page: 'custom page name'}): the form of Navigate that Learn shows for opening a custom page with a record.</summary>
    private sealed class NavigateRecordPage(List<string> calls) : ReflectionFunction("Navigate", FormulaType.Boolean, RecordType.Empty(), PageOption)
    {
        public BooleanValue Execute(RecordValue record, RecordValue options)
        {
            calls.Add($"Navigate({((StringValue)record.GetField("cin_name")).Value}, Page={((StringValue)options.GetField("Page")).Value})");
            return FormulaValue.New(true);
        }
    }

    /// <summary>Param("id"): what a custom page receives from Navigate(record, {Page: ...}); Learn shows Param("etn") and Param("id").</summary>
    private sealed class ParamFunction(Dictionary<string, string> values) : ReflectionFunction("Param", FormulaType.String, FormulaType.String)
    {
        public StringValue Execute(StringValue name) => FormulaValue.New(values.TryGetValue(name.Value, out var v) ? v : "");
    }
}
