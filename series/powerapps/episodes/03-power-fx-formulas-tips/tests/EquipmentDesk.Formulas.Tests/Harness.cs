using System.Globalization;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Core;
using Microsoft.PowerFx.Core.Utils;
using Microsoft.PowerFx.Functions;
using Microsoft.PowerFx.Types;

namespace EquipmentDesk.Formulas.Tests;

/// <summary>
/// Runs App.Formulas and the Loans screen on Microsoft's open-source Power Fx interpreter, against in-memory tables shaped
/// like the Dataverse tables from episode 1 (same display names, local choices, a lookup from Loan to Equipment).
/// The clock is fixed, so Today() is always Monday 30 November 2026 unless a test moves it. Copy and Notify are stubs
/// that record their calls. This tests formula LOGIC; delegation is only linted (see DelegationLintTests).
/// </summary>
public sealed class Harness
{
    public static readonly DateTime DefaultToday = new(2026, 11, 30); // a Monday; 1 December is a public holiday in Portugal

    public RecalcEngine Engine { get; }
    public OptionSet Status { get; }
    public OptionSet Category { get; }
    public RecordType EquipmentType { get; }
    public RecordType LoanType { get; }
    public TableValue Equipment { get; private set; } = null!;
    public TableValue Loans { get; private set; } = null!;
    public List<string> Calls { get; } = new();
    public DefinitionsCheckResult FunctionsResult { get; private set; } = null!;
    public CanvasSource Source { get; }

    private readonly RuntimeConfig runtime = new();
    private readonly FixedClock clock = new(DefaultToday);
    private readonly CopyFunction copy;
    private static readonly ParserOptions Behavior = new() { AllowsSideEffects = true };

    public Harness(CanvasSource source, string userLanguage = "en-GB")
    {
        Source = source;
        var config = new PowerFxConfig();
        var symbols = new SymbolTable();
        config.SymbolTable = symbols;
        config.EnableSetFunction();

        Status = new OptionSet("Status (Equipment)", DisplayNameUtility.MakeUnique(new Dictionary<string, string>
            { ["Available"] = "Available", ["OnLoan"] = "On loan", ["InRepair"] = "In repair", ["Retired"] = "Retired" }));
        Category = new OptionSet("Category (Equipment)", DisplayNameUtility.MakeUnique(new Dictionary<string, string>
            { ["Laptop"] = "Laptop", ["Monitor"] = "Monitor", ["Phone"] = "Phone", ["Accessory"] = "Accessory" }));
        config.AddOptionSet(Status);
        config.AddOptionSet(Category);

        copy = new CopyFunction(Calls);
        config.AddFunction(copy);
        config.AddFunction(new NotifyFunction(Calls));

        Engine = new RecalcEngine(config);
        runtime.AddService<IClockService>(clock);
        runtime.AddService(TimeZoneInfo.Utc);
        runtime.SetCulture(new CultureInfo(userLanguage)); // what Language() would return for the user running the app

        EquipmentType = RecordType.Empty()
            .Add("contoso_name", FormulaType.String, "Name")
            .Add("contoso_assettag", FormulaType.String, "Asset tag")
            .Add("contoso_category", Category.FormulaType, "Category")
            .Add("contoso_status", Status.FormulaType, "Status");
        LoanType = RecordType.Empty()
            .Add("contoso_name", FormulaType.String, "Loan")
            .Add("contoso_equipmentid", EquipmentType, "Equipment")
            .Add("contoso_borroweremail", FormulaType.String, "Borrower email")
            .Add("contoso_loandate", FormulaType.Date, "Loan date")
            .Add("contoso_duedate", FormulaType.Date, "Due date")
            .Add("contoso_returnedon", FormulaType.Date, "Returned on")
            .Add("contoso_notes", FormulaType.String, "Notes");

        Equipment = FormulaValue.NewTable(EquipmentType,
            Device("CT-0042", "Laptop 14", "Laptop", "Available"),
            Device("CT-0043", "Laptop 14", "Laptop", "OnLoan"),
            Device("CT-0107", "Monitor 27", "Monitor", "OnLoan"),
            Device("CT-0108", "Monitor 24", "Monitor", "OnLoan"),
            Device("CT-0311", "Phone", "Phone", "OnLoan"));

        // Today is Mon 30 Nov 2026. One loan of each state, and one returned loan that must never show.
        Loans = FormulaValue.NewTable(LoanType,
            Loan("CT-0043", "alex.demo@contoso.com", new(2026, 11, 2), new(2026, 11, 16), null, "Charger missing"),
            Loan("CT-0107", "jordan.demo@contoso.com", new(2026, 11, 13), new(2026, 11, 27), null, null),
            Loan("CT-0108", "sam.demo@contoso.com", new(2026, 11, 18), new(2026, 12, 2), null, ""),
            Loan("CT-0311", "alex.demo@contoso.com", new(2026, 11, 23), new(2026, 12, 18), null, null),
            Loan("CT-0042", "jordan.demo@contoso.com", new(2026, 11, 2), new(2026, 11, 16), new(2026, 11, 20), "Returned with dock"));
        Engine.UpdateVariable("Equipment", Equipment);
        Engine.UpdateVariable("Loans", Loans);

        Enum("NotificationType", "Success", "Error", "Warning", "Information");
        Enum("FontWeight", "Normal", "Semibold", "Bold");

        SetControl("tglOverdueOnly", ("Value", FormulaValue.New(false)));
        LoadFormulas();
    }

    /// <summary>
    /// Named formulas are evaluated (in dependency order, retrying until nothing changes) and stored as values; then all
    /// UDFs are added in one call so they can call each other. In Power Apps named formulas recalculate on their own;
    /// here a test calls <see cref="Recalc"/> after it changes data or the clock.
    /// </summary>
    private void LoadFormulas()
    {
        Recalc();
        var udfs = string.Join("\n", Source.Definitions().Where(d => d.Kind != CanvasSource.DefinitionKind.NamedFormula).Select(d => d.Text + ";"));
        FunctionsResult = Engine.AddUserDefinedFunction(udfs, CultureInfo.InvariantCulture, Engine.EngineSymbols, allowSideEffects: true);
        Recalc(); // named formulas that call UDFs
    }

    public void Recalc()
    {
        var pending = Source.Definitions().Where(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula).ToList();
        while (pending.Count > 0)
        {
            var done = pending.Where(d => Engine.Check(d.Expression, Behavior).IsSuccess).ToList();
            if (done.Count == 0) return; // the rest need UDFs (or are broken: SourceTests checks that every formula binds)
            foreach (var d in done) Engine.UpdateVariable(d.Name, Eval(d.Expression));
            pending = pending.Except(done).ToList();
        }
    }

    public void SetToday(DateTime day) { clock.UtcNow = day.Date; Recalc(); }

    public void ClipboardUnavailable(string message) => copy.FailWith = message;

    public RecordValue Device(string tag, string name, string category, string status) =>
        FormulaValue.NewRecordFromFields(EquipmentType,
            new NamedValue("contoso_name", FormulaValue.New(name)),
            new NamedValue("contoso_assettag", FormulaValue.New(tag)),
            new NamedValue("contoso_category", Option(Category, category)),
            new NamedValue("contoso_status", Option(Status, status)));

    public RecordValue Loan(string tag, string email, DateTime loanDate, DateTime due, DateTime? returned, string? notes) =>
        FormulaValue.NewRecordFromFields(LoanType,
            new NamedValue("contoso_name", FormulaValue.New($"{tag} - {email.Split('@')[0]} - {loanDate:yyyy-MM-dd}")),
            new NamedValue("contoso_equipmentid", Equipment.Rows.Select(r => r.Value).First(r => ((StringValue)r.GetField("contoso_assettag")).Value == tag)),
            new NamedValue("contoso_borroweremail", FormulaValue.New(email)),
            new NamedValue("contoso_loandate", FormulaValue.NewDateOnly(loanDate)),
            new NamedValue("contoso_duedate", FormulaValue.NewDateOnly(due)),
            new NamedValue("contoso_returnedon", returned is { } r ? FormulaValue.NewDateOnly(r) : FormulaValue.NewBlank(FormulaType.Date)),
            new NamedValue("contoso_notes", notes is null ? FormulaValue.NewBlank(FormulaType.String) : FormulaValue.New(notes)));

    public static OptionSetValue Option(OptionSet set, string logicalName) =>
        set.TryGetValue(new DName(logicalName), out var v) ? v : throw new ArgumentException(logicalName);

    public void SetControl(string name, params (string Property, FormulaValue Value)[] props) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(props.Select(p => new NamedValue(p.Property, p.Value))));

    /// <summary>Gallery template formulas see the row as ThisItem.</summary>
    public void SetThisItem(RecordValue row) => Engine.UpdateVariable("ThisItem", row);

    public RecordValue LoanFor(string tag) =>
        Loans.Rows.Select(r => r.Value).First(r => ((StringValue)((RecordValue)r.GetField("contoso_equipmentid")).GetField("contoso_assettag")).Value == tag
                                                   && r.GetField("contoso_returnedon") is BlankValue);

    public FormulaValue Eval(string formula)
    {
        var result = Engine.EvalAsync(formula, CancellationToken.None, Behavior, null, runtime).GetAwaiter().GetResult();
        return result is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : result;
    }

    public string Text(string formula) => Eval(formula) switch { StringValue s => s.Value, BlankValue => "", var v => v.ToObject()?.ToString() ?? "" };
    public decimal Number(string formula) => Eval(formula) switch { DecimalValue d => d.Value, NumberValue n => (decimal)n.Value, var v => throw new InvalidCastException(v.GetType().Name) };
    public bool Bool(string formula) => ((BooleanValue)Eval(formula)).Value;

    public CheckResult Check(string formula) => Engine.Check(formula, Behavior);

    /// <summary>Asset tags of a table of loans, in order.</summary>
    public IEnumerable<string> Tags(TableValue loans) =>
        loans.Rows.Select(r => ((StringValue)((RecordValue)r.Value.GetField("contoso_equipmentid")).GetField("contoso_assettag")).Value);

    private void Enum(string name, params string[] members) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(members.Select(m => new NamedValue(m, FormulaValue.New(m)))));

    /// <summary>Today() is the date of UtcNow in the user's time zone; the harness runs in UTC.</summary>
    private sealed class FixedClock(DateTime day) : IClockService
    {
        private DateTime utcNow = DateTime.SpecifyKind(day.Date.AddHours(9), DateTimeKind.Utc);
        public DateTime UtcNow { get => utcNow; set => utcNow = DateTime.SpecifyKind(value.Date.AddHours(9), DateTimeKind.Utc); }
    }

    private sealed class NotifyFunction(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message, StringValue type) { calls.Add($"Notify({type.Value}): {message.Value}"); return FormulaValue.New(true); }
    }

    /// <summary>Copy(text). Fails like an embedded host without clipboard access (Learn: Teams, SharePoint, Power BI) when told to.</summary>
    private sealed class CopyFunction(List<string> calls) : ReflectionFunction("Copy", FormulaType.Boolean, FormulaType.String)
    {
        public string? FailWith { get; set; }

        public FormulaValue Execute(StringValue text)
        {
            if (FailWith != null) return FormulaValue.NewError(new ExpressionError { Message = FailWith, Kind = ErrorKind.NotSupported });
            calls.Add($"Copy: {text.Value}");
            return FormulaValue.New(true);
        }
    }
}
