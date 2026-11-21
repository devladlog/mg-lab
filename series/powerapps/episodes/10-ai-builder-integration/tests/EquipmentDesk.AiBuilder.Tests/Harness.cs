using System.Globalization;
using System.Text.RegularExpressions;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Core;
using Microsoft.PowerFx.Core.Utils;
using Microsoft.PowerFx.Functions;
using Microsoft.PowerFx.Types;

namespace EquipmentDesk.AiBuilder.Tests;

/// <summary>
/// Runs the Equipment Desk triage formulas and the Return check screen on Microsoft's open-source Power Fx interpreter
/// (1.8.1) with in-memory Dataverse-shaped tables (same as episodes 2 to 8) and a fixed clock (Today() = Monday 30 November 2026).
///
/// The one thing that can't run here is the AI Builder prompt itself: 'ReturnNoteTriage'.Predict(...) needs a tenant and
/// consumes credits. The harness rewrites that call to ReturnNoteTriage__Predict(...) (Power Fx names can't contain a dot)
/// and registers a test double that returns whatever <see cref="ModelAnswer"/> says, and records every input it received.
/// That rewrite is the only liberty taken with the source formulas; a test checks it doesn't touch anything else.
/// </summary>
public sealed class Harness
{
    public static readonly DateTime DefaultToday = new(2026, 11, 30);
    private static readonly ParserOptions Behavior = new() { AllowsSideEffects = true };

    public CanvasSource App { get; }
    public RecalcEngine Engine { get; }
    public OptionSet Status { get; }
    public RecordType EquipmentType { get; }
    public RecordType LoanType { get; }
    public List<string> Calls { get; } = new();
    /// <summary>Every text the app sent to the prompt, in order.</summary>
    public List<string> PredictInputs { get; } = new();
    /// <summary>What the prompt answers. Return null to simulate a failed call (throttling, no capacity, region).</summary>
    public Func<string, string?> ModelAnswer { get; set; } = _ => null;
    public DefinitionsCheckResult FunctionsResult { get; private set; } = null!;
    public TableValue Equipment => (TableValue)dataValues.Get(equipmentSlot);
    public TableValue Loans => (TableValue)dataValues.Get(loansSlot);

    private readonly SymbolTable dataSymbols = new();
    private readonly ReadOnlySymbolValues dataValues;
    private readonly ISymbolSlot equipmentSlot, loansSlot;
    private readonly RuntimeConfig runtime;
    private readonly FixedClock clock = new(DefaultToday);

    public Harness(CanvasSource app)
    {
        App = app;
        var config = new PowerFxConfig();
        var symbols = new SymbolTable();
        symbols.EnableMutationFunctions();
        config.SymbolTable = symbols;
        config.EnableSetFunction();
        config.EnableJsonFunctions();

        Status = new OptionSet("Status (Equipment)", DisplayNameUtility.MakeUnique(new Dictionary<string, string>
            { ["Available"] = "Available", ["OnLoan"] = "On loan", ["InRepair"] = "In repair", ["Retired"] = "Retired" }));
        config.AddOptionSet(Status);

        config.AddFunction(new NotifyFunction(Calls));
        config.AddFunction(new BackFunction(Calls));
        config.AddFunction(new PredictFunction(this));

        Engine = new RecalcEngine(config);

        EquipmentType = RecordType.Empty()
            .Add("contoso_equipmentid", FormulaType.Guid, "Equipment")
            .Add("contoso_name", FormulaType.String, "Name")
            .Add("contoso_assettag", FormulaType.String, "Asset tag")
            .Add("contoso_status", Status.FormulaType, "Status");
        LoanType = RecordType.Empty()
            .Add("contoso_loanid", FormulaType.Guid, "Loan ID")
            .Add("contoso_name", FormulaType.String, "Loan")
            .Add("contoso_equipmentid", EquipmentType, "Equipment")
            .Add("contoso_borroweremail", FormulaType.String, "Borrower email")
            .Add("contoso_loandate", FormulaType.Date, "Loan date")
            .Add("contoso_duedate", FormulaType.Date, "Due date")
            .Add("contoso_returnedon", FormulaType.Date, "Returned on")
            .Add("contoso_notes", FormulaType.String, "Notes");

        var equipment = FormulaValue.NewTable(EquipmentType,
            Device(1, "CT-0042", "Laptop 14", "Available"),
            Device(2, "CT-0043", "Laptop 14", "OnLoan"),
            Device(3, "CT-0107", "Monitor 27", "OnLoan"));
        var mutable = new SymbolProperties { CanMutate = true };
        equipmentSlot = dataSymbols.AddVariable("Equipment", EquipmentType.ToTable(), mutable);
        loansSlot = dataSymbols.AddVariable("Loans", LoanType.ToTable(), mutable);
        dataValues = dataSymbols.CreateValues();
        dataValues.Set(equipmentSlot, equipment);
        dataValues.Set(loansSlot, FormulaValue.NewTable(LoanType,
            Loan(11, "CT-0043", "alex.demo@contoso.com", new(2026, 11, 2), new(2026, 11, 16), null, "Charger missing"),
            Loan(12, "CT-0107", "jordan.demo@contoso.com", new(2026, 11, 18), new(2026, 12, 2), null, null),
            Loan(14, "CT-0042", "riley.demo@contoso.com", new(2026, 11, 2), new(2026, 11, 16), new(2026, 11, 20), null)));

        runtime = new RuntimeConfig(dataValues);
        runtime.AddService<IClockService>(clock);
        runtime.AddService(TimeZoneInfo.Utc);
        runtime.SetCulture(new CultureInfo("en-GB"));

        Enum("NotificationType", "Success", "Error", "Warning", "Information");
        Enum("FontWeight", "Normal", "Semibold", "Bold");
        Enum("DisplayMode", "Edit", "View", "Disabled");
        Enum("TextMode", "SingleLine", "MultiLine", "Password");

        Engine.UpdateVariable("returnLoan", OpenLoan("CT-0043"));
        Engine.UpdateVariable("triageRaw", FormulaValue.New(""));
        Engine.UpdateVariable("checking", FormulaValue.New(false));
        SetNote("");
        SetStatusPicker("Available");

        LoadFormulas();
    }

    private void LoadFormulas()
    {
        Recalc();
        var udfs = string.Join("\n", App.Definitions().Where(d => d.Kind == CanvasSource.DefinitionKind.Function).Select(d => d.Text + ";"));
        FunctionsResult = Engine.AddUserDefinedFunction(udfs, CultureInfo.InvariantCulture, Engine.EngineSymbols);
        Recalc();
    }

    /// <summary>Evaluates the App.Formulas named formulas in dependency order.</summary>
    public void Recalc()
    {
        var pending = App.Definitions().Where(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula).ToList();
        while (pending.Count > 0)
        {
            var done = pending.Where(d => Check(d.Expression).IsSuccess).ToList();
            if (done.Count == 0) return;
            foreach (var d in done) Engine.UpdateVariable(d.Name, Eval(d.Expression));
            pending = pending.Except(done).ToList();
        }
    }

    private static readonly Regex PredictCall = new(@"'ReturnNoteTriage'\.Predict\(", RegexOptions.Compiled);

    /// <summary>'ReturnNoteTriage'.Predict( -> ReturnNoteTriage__Predict( ; nothing else is changed.</summary>
    public static string Rewrite(string formula) => PredictCall.Replace(formula, "ReturnNoteTriage__Predict(");

    public FormulaValue Eval(string formula)
    {
        var result = Engine.EvalAsync(Rewrite(formula), CancellationToken.None, Behavior, dataSymbols, runtime).GetAwaiter().GetResult();
        return result is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : result;
    }

    public CheckResult Check(string formula) => Engine.Check(Rewrite(formula), Behavior, dataSymbols);

    public string Text(string formula) => Eval(formula) switch { StringValue s => s.Value, BlankValue => "", var v => v.ToObject()?.ToString() ?? "" };
    public bool Bool(string formula) => Eval(formula) switch { BooleanValue b => b.Value, BlankValue => false, var v => throw new InvalidCastException(v.GetType().Name) };
    public decimal Number(string formula) => Eval(formula) switch { DecimalValue d => d.Value, NumberValue n => (decimal)n.Value, var v => throw new InvalidCastException(v.GetType().Name) };

    /// <summary>Calls an App.Formulas function with a text argument, e.g. Fn("TriageCondition", json).</summary>
    public FormulaValue Fn(string name, string arg) =>
        Eval($"{name}(\"{arg.Replace("\"", "\"\"")}\")");

    public string FnText(string name, string arg) => Fn(name, arg) switch { StringValue s => s.Value, var v => v.ToObject()?.ToString() ?? "" };

    /// <summary>Runs a control property of the Return check screen (behavior formulas such as OnSelect included).</summary>
    public FormulaValue Run(string control, string property) => Eval(App.Formula(control, property));

    // ---- controls -------------------------------------------------------------------------------------------------

    public void SetNote(string text) =>
        Engine.UpdateVariable("txtNote", FormulaValue.NewRecordFromFields(new NamedValue("Text", FormulaValue.New(text))));

    public void SetStatusPicker(string value) =>
        Engine.UpdateVariable("drpStatus", FormulaValue.NewRecordFromFields(new NamedValue("Selected",
            FormulaValue.NewRecordFromFields(new NamedValue("Value", FormulaValue.New(value))))));

    /// <summary>The dropdown the way Studio shows it right after the app sets Default.</summary>
    public string DropdownDefault() => Text(App.Formula("drpStatus", "Default"));

    public string TriageRaw => Text("triageRaw");

    // ---- data -------------------------------------------------------------------------------------------------------

    public static Guid Id(int n) => new($"00000000-0000-0000-0000-{n:D12}");

    public RecordValue Device(int id, string tag, string name, string status) =>
        FormulaValue.NewRecordFromFields(EquipmentType,
            new NamedValue("contoso_equipmentid", FormulaValue.New(Id(id))),
            new NamedValue("contoso_name", FormulaValue.New(name)),
            new NamedValue("contoso_assettag", FormulaValue.New(tag)),
            new NamedValue("contoso_status", Option(status)));

    public RecordValue Loan(int id, string tag, string email, DateTime loanDate, DateTime due, DateTime? returned, string? notes) =>
        FormulaValue.NewRecordFromFields(LoanType,
            new NamedValue("contoso_loanid", FormulaValue.New(Id(id))),
            new NamedValue("contoso_name", FormulaValue.New($"{tag} - {email.Split('@')[0]} - {loanDate:yyyy-MM-dd}")),
            new NamedValue("contoso_equipmentid", Equipment.Rows.Select(r => r.Value).First(r => Field(r, "contoso_assettag") == tag)),
            new NamedValue("contoso_borroweremail", FormulaValue.New(email)),
            new NamedValue("contoso_loandate", FormulaValue.NewDateOnly(loanDate)),
            new NamedValue("contoso_duedate", FormulaValue.NewDateOnly(due)),
            new NamedValue("contoso_returnedon", returned is { } r ? FormulaValue.NewDateOnly(r) : FormulaValue.NewBlank(FormulaType.Date)),
            new NamedValue("contoso_notes", notes is null ? FormulaValue.NewBlank(FormulaType.String) : FormulaValue.New(notes)));

    public OptionSetValue Option(string logicalName) =>
        Status.TryGetValue(new DName(logicalName), out var v) ? v : throw new ArgumentException(logicalName);

    public static string Field(RecordValue r, string name) => r.GetField(name) switch
    {
        StringValue s => s.Value,
        BlankValue => "",
        OptionSetValue o => o.Option,
        DateValue d => d.GetConvertedValue(TimeZoneInfo.Utc).ToString("yyyy-MM-dd"),
        var v => v.ToObject()?.ToString() ?? "",
    };

    public RecordValue OpenLoan(string tag) =>
        Loans.Rows.Select(r => r.Value).First(r => Field((RecordValue)r.GetField("contoso_equipmentid"), "contoso_assettag") == tag
                                                   && r.GetField("contoso_returnedon") is BlankValue);

    public RecordValue LoanRow(string tag) =>
        Loans.Rows.Select(r => r.Value).Last(r => Field((RecordValue)r.GetField("contoso_equipmentid"), "contoso_assettag") == tag);

    public RecordValue DeviceRow(string tag) => Equipment.Rows.Select(r => r.Value).First(r => Field(r, "contoso_assettag") == tag);

    public void MakeReadOnly(string table, string message)
    {
        var slot = table == "Loans" ? loansSlot : equipmentSlot;
        dataValues.Set(slot, new ReadOnlyTable((TableValue)dataValues.Get(slot), message));
    }

    private void Enum(string name, params string[] members) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(members.Select(m => new NamedValue(m, FormulaValue.New(m)))));

    private sealed class FixedClock(DateTime day) : IClockService
    {
        public DateTime UtcNow { get; set; } = DateTime.SpecifyKind(day.Date.AddHours(9), DateTimeKind.Utc);
    }

    private sealed class NotifyFunction(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message, StringValue type) { calls.Add($"Notify({type.Value}): {message.Value}"); return FormulaValue.New(true); }
    }

    private sealed class BackFunction(List<string> calls) : ReflectionFunction("Back", FormulaType.Boolean)
    {
        public BooleanValue Execute() { calls.Add("Back()"); return FormulaValue.New(true); }
    }

    /// <summary>Test double for 'ReturnNoteTriage'.Predict(note): returns { text: ... } like the real prompt, or an error.</summary>
    private sealed class PredictFunction(Harness h)
        : ReflectionFunction("ReturnNoteTriage__Predict", RecordType.Empty().Add("text", FormulaType.String), FormulaType.String)
    {
        public FormulaValue Execute(StringValue note)
        {
            h.PredictInputs.Add(note.Value);
            var answer = h.ModelAnswer(note.Value);
            return answer is null
                ? FormulaValue.NewError(new ExpressionError { Message = "No capacity was found (test double)", Kind = ErrorKind.Network })
                : FormulaValue.NewRecordFromFields(new NamedValue("text", FormulaValue.New(answer)));
        }
    }
}
