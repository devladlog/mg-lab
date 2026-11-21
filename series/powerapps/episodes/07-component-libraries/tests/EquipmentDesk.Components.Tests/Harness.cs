using System.Globalization;
using System.Text.RegularExpressions;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Core;
using Microsoft.PowerFx.Core.Utils;
using Microsoft.PowerFx.Functions;
using Microsoft.PowerFx.Types;

namespace EquipmentDesk.Components.Tests;

/// <summary>
/// Runs the Equipment Desk app formulas AND the Equipment Desk Kit component definitions on Microsoft's open-source
/// Power Fx interpreter (1.8.1), with in-memory Dataverse-shaped tables (same as episodes 2-6) and a fixed clock
/// (Today() = Monday 30 November 2026).
///
/// How components are hosted here (Power Apps does this itself; the open-source engine knows nothing about components):
/// - Inside a component, its inputs are read as DefinitionName.Property. Before a component formula runs, the harness
///   evaluates the instance's input formulas (or the definition's Default) in the app and stores them as a record
///   variable named after the definition (e.g. ConfirmDialog = { Title: ..., Message: ..., ... }).
/// - Function-like properties are called as Name.Prop(...). Power Fx names can't contain a dot, so the harness rewrites
///   those calls to Name__Prop(...) before evaluating:
///     OutputFunction  inst.StateColor(x)   -> a UDF built from the definition (parameters, ReturnType, formula)
///     Event           Def.OnConfirm()      -> a function that runs the current instance's handler formula in the app
/// That rewrite is the only liberty taken with the source formulas; a test checks it doesn't touch anything else.
/// </summary>
public sealed class Harness
{
    public static readonly DateTime DefaultToday = new(2026, 11, 30);

    public CanvasSource App { get; }
    public CanvasSource Library { get; }
    public RecalcEngine Engine { get; }
    public OptionSet Status { get; }
    public RecordType EquipmentType { get; }
    public RecordType LoanType { get; }
    public List<string> Calls { get; } = new();
    public DefinitionsCheckResult AppFunctionsResult { get; private set; } = null!;
    public DefinitionsCheckResult ComponentFunctionsResult { get; private set; } = null!;
    public TableValue Equipment => (TableValue)dataValues.Get(equipmentSlot);
    public TableValue Loans => (TableValue)dataValues.Get(loansSlot);

    private readonly SymbolTable dataSymbols = new();
    private readonly ReadOnlySymbolValues dataValues;
    private readonly ISymbolSlot equipmentSlot, loansSlot;
    private readonly RuntimeConfig runtime;
    private readonly FixedClock clock = new(DefaultToday);
    private readonly Dictionary<string, CanvasSource.ControlInfo> instances = new();
    /// <summary>Owner name (instance or definition) -> function-like property names, for the call rewrite.</summary>
    private readonly Dictionary<string, HashSet<string>> callable = new();
    /// <summary>Definition name -> the instance whose formulas are "inside" right now (events go to its handlers).</summary>
    private readonly Dictionary<string, string> current = new();
    private static readonly ParserOptions Behavior = new() { AllowsSideEffects = true };

    public Harness(CanvasSource app, CanvasSource library)
    {
        App = app;
        Library = library;
        foreach (var i in app.Instances.Concat(library.Instances)) instances[i.Name] = i;

        var config = new PowerFxConfig();
        var symbols = new SymbolTable();
        symbols.EnableMutationFunctions();
        config.SymbolTable = symbols;
        config.EnableSetFunction();
        config.EnableRegExFunctions(TimeSpan.FromSeconds(1), 50);

        Status = new OptionSet("Status (Equipment)", DisplayNameUtility.MakeUnique(new Dictionary<string, string>
            { ["Available"] = "Available", ["OnLoan"] = "On loan", ["InRepair"] = "In repair", ["Retired"] = "Retired" }));
        config.AddOptionSet(Status);

        config.AddFunction(new NotifyFunction(Calls));
        config.AddFunction(new BackFunction(Calls));
        config.AddFunction(new CopyFunction(Calls));

        // Events: one dispatcher per (definition, event); it runs the handler of whichever instance is current.
        foreach (var def in library.Components.Values)
        {
            foreach (var p in def.CustomProperties.Values.Where(p => p.IsFunctionLike)) Callable(def.Name).Add(p.Name);
            foreach (var e in def.CustomProperties.Values.Where(p => p.Kind == "Event"))
                config.AddFunction(new EventFunction($"{def.Name}__{e.Name}", () => Fire(def.Name, e.Name)));
        }
        foreach (var inst in instances.Values)
            foreach (var p in Definition(inst).CustomProperties.Values.Where(p => p.Kind is "OutputFunction"))
                Callable(inst.Name).Add(p.Name);

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
            Device(3, "CT-0107", "Monitor 27", "OnLoan"),
            Device(4, "CT-0108", "Monitor 24", "OnLoan"));
        var mutable = new SymbolProperties { CanMutate = true };
        equipmentSlot = dataSymbols.AddVariable("Equipment", EquipmentType.ToTable(), mutable);
        loansSlot = dataSymbols.AddVariable("Loans", LoanType.ToTable(), mutable);
        dataValues = dataSymbols.CreateValues();
        dataValues.Set(equipmentSlot, equipment);
        // Today is Mon 30 Nov 2026: one overdue, one due soon, one on loan, one already returned.
        dataValues.Set(loansSlot, FormulaValue.NewTable(LoanType,
            Loan(11, "CT-0043", "alex.demo@contoso.com", new(2026, 11, 2), new(2026, 11, 16), null, "Charger missing"),
            Loan(12, "CT-0107", "jordan.demo@contoso.com", new(2026, 11, 18), new(2026, 12, 2), null, null),
            Loan(13, "CT-0108", "sam.demo@contoso.com", new(2026, 11, 23), new(2026, 12, 18), null, ""),
            Loan(14, "CT-0042", "riley.demo@contoso.com", new(2026, 11, 2), new(2026, 11, 16), new(2026, 11, 20), null)));

        runtime = new RuntimeConfig(dataValues);
        runtime.AddService<IClockService>(clock);
        runtime.AddService(TimeZoneInfo.Utc);
        runtime.SetCulture(new CultureInfo("en-GB"));

        Enum("NotificationType", "Success", "Error", "Warning", "Information");
        Enum("FontWeight", "Normal", "Semibold", "Bold");
        Enum("DisplayMode", "Edit", "View", "Disabled");
        Enum("Icon", "ChevronLeft", "Cancel", "Check");
        Enum("TextRole", "Default", "Heading1", "Heading2", "Heading3", "Heading4");
        Enum("VerticalAlign", "Top", "Middle", "Bottom");

        Engine.UpdateVariable("returnLoan", FormulaValue.NewBlank(LoanType));
        Engine.UpdateVariable("sendingLoan", FormulaValue.NewBlank(FormulaType.Guid));
        Engine.UpdateVariable("lastEvent", FormulaValue.NewBlank(FormulaType.String));
        Engine.UpdateVariable("showDialog", FormulaValue.New(false));
        SetControl("tglOverdueOnly", ("Value", FormulaValue.New(false)));

        // Stand-in for the Contoso Holidays connector (episode 5): DaysOff is the connector's answer, so the harness
        // sets it as a value instead of evaluating ContosoHolidays.GetDaysOff(...).
        var day = RecordType.Empty().Add("date", FormulaType.Date);
        Engine.UpdateVariable("DaysOff", FormulaValue.NewRecordFromFields(new NamedValue("days", FormulaValue.NewTable(day,
            new[] { new DateTime(2026, 12, 1), new DateTime(2026, 12, 8), new DateTime(2026, 12, 25) }
                .Select(d => FormulaValue.NewRecordFromFields(day, new NamedValue("date", FormulaValue.NewDateOnly(d))))))));

        LoadFormulas();
    }

    private HashSet<string> Callable(string owner) => callable.TryGetValue(owner, out var s) ? s : callable[owner] = new();

    public CanvasSource.ComponentDefinition Definition(CanvasSource.ControlInfo instance) =>
        Library.Components[instance.ComponentName ?? throw new InvalidOperationException($"{instance.Name} has no ComponentName")];

    public CanvasSource.ControlInfo Instance(string name) => instances[name];

    private void LoadFormulas()
    {
        Recalc();
        var udfs = string.Join("\n", App.Definitions().Where(d => d.Kind != CanvasSource.DefinitionKind.NamedFormula).Select(d => d.Text + ";"));
        AppFunctionsResult = Engine.AddUserDefinedFunction(udfs, CultureInfo.InvariantCulture, Engine.EngineSymbols, allowSideEffects: true);
        ComponentFunctionsResult = Engine.AddUserDefinedFunction(string.Join("\n", OutputFunctionUdfs()), CultureInfo.InvariantCulture, Engine.EngineSymbols);
        Recalc();
    }

    /// <summary>inst__Prop(p: Type, ...): ReturnType = formula; for every OutputFunction of every instance.</summary>
    public IEnumerable<string> OutputFunctionUdfs() =>
        from inst in instances.Values
        let def = Definition(inst)
        from p in def.CustomProperties.Values
        where p.Kind == "OutputFunction"
        select Udf($"{inst.Name}__{p.Name}", p, def.Properties[p.Name]);

    public static string Udf(string name, CanvasSource.CustomProperty p, string formula) =>
        $"{name}({string.Join(", ", p.Parameters.Select(a => $"{a.Name}: {FxType(a.DataType)}"))}): {FxType(p.ReturnType!)} = {CanvasSource.Strip(formula)};";

    /// <summary>pa.yaml data types -> Power Fx type names usable in a UDF signature.</summary>
    public static string FxType(string dataType) => dataType switch
    {
        "Text" => "Text",
        "Number" or "Currency" => "Number",
        "Boolean" => "Boolean",
        "Color" => "Color",
        "DateAndTime" => "DateTime",
        "None" => "Void",
        _ => throw new NotSupportedException($"data type {dataType} isn't mapped in the harness"),
    };

    /// <summary>Evaluates App.Formulas named formulas (except DaysOff, set above) in dependency order.</summary>
    public void Recalc()
    {
        var pending = App.Definitions().Where(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula && d.Name != "DaysOff").ToList();
        while (pending.Count > 0)
        {
            var done = pending.Where(d => Check(d.Expression).IsSuccess).ToList();
            if (done.Count == 0) return;
            foreach (var d in done) Engine.UpdateVariable(d.Name, Eval(d.Expression));
            pending = pending.Except(done).ToList();
        }
    }

    private static readonly Regex Call = new(@"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)(\s*\()", RegexOptions.Compiled);

    /// <summary>Owner.Prop( -> Owner__Prop( for function-like component properties; everything else is left alone.</summary>
    public string Rewrite(string formula) =>
        Call.Replace(formula, m => callable.TryGetValue(m.Groups[1].Value, out var props) && props.Contains(m.Groups[2].Value)
            ? $"{m.Groups[1].Value}__{m.Groups[2].Value}{m.Groups[3].Value}"
            : m.Value);

    // ---- app context -------------------------------------------------------------------------------------------

    public FormulaValue Eval(string formula)
    {
        var result = Engine.EvalAsync(Rewrite(formula), CancellationToken.None, Behavior, dataSymbols, runtime).GetAwaiter().GetResult();
        return result is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : result;
    }

    public CheckResult Check(string formula) => Engine.Check(Rewrite(formula), Behavior, dataSymbols);

    public string Text(string formula) => Eval(formula) switch { StringValue s => s.Value, BlankValue => "", var v => v.ToObject()?.ToString() ?? "" };
    public bool Bool(string formula) => Eval(formula) switch { BooleanValue b => b.Value, BlankValue => false, var v => throw new InvalidCastException(v.GetType().Name) };
    public decimal Number(string formula) => Eval(formula) switch { DecimalValue d => d.Value, NumberValue n => (decimal)n.Value, var v => throw new InvalidCastException(v.GetType().Name) };
    public string Color(string formula) => Eval(formula) is ColorValue c ? Hex(c.Value) : throw new InvalidCastException();

    public static string Hex(System.Drawing.Color c) => $"#{c.R:X2}{c.G:X2}{c.B:X2}{c.A:X2}";

    /// <summary>Runs an app control property (behavior formulas such as OnSelect included).</summary>
    public FormulaValue Run(string control, string property) => Eval(App.Formula(control, property));

    /// <summary>An instance property as set in the app (or the definition's default when the app doesn't set it).</summary>
    public FormulaValue InstanceValue(string instance, string property)
    {
        var inst = instances[instance];
        if (inst.Properties.TryGetValue(property, out var f)) return Eval(CanvasSource.Strip(f));
        var d = Definition(inst).CustomProperties[property].Default;
        return d is null ? FormulaValue.NewBlank() : Eval(CanvasSource.Strip(d));
    }

    // ---- component context -------------------------------------------------------------------------------------

    /// <summary>
    /// Makes formulas inside the instance's definition see this instance's inputs (DefinitionName.Input) and send its
    /// events to this instance's handlers.
    /// </summary>
    public void Enter(string instance)
    {
        var inst = instances[instance];
        var def = Definition(inst);
        var inputs = def.CustomProperties.Values.Where(p => p.Kind == "Input")
            .Select(p => new NamedValue(p.Name, InstanceValue(instance, p.Name)));
        Engine.UpdateVariable(def.Name, FormulaValue.NewRecordFromFields(inputs));
        current[def.Name] = instance;
    }

    /// <summary>A component formula as a fresh instance would see it: every input at its Default, no event handlers.</summary>
    public FormulaValue InsideDefaults(string definition, string control, string property)
    {
        var def = Library.Components[definition];
        var inputs = def.CustomProperties.Values.Where(p => p.Kind == "Input")
            .Select(p => new NamedValue(p.Name, p.Default is null ? FormulaValue.NewBlank() : Eval(CanvasSource.Strip(p.Default))));
        Engine.UpdateVariable(def.Name, FormulaValue.NewRecordFromFields(inputs));
        current.Remove(def.Name);
        return Eval(CanvasSource.Strip(Library.Controls[control].Properties[property]));
    }

    /// <summary>Binds a component formula with the definition's inputs in scope (defaults).</summary>
    public CheckResult CheckInside(string definition, string formula)
    {
        var def = Library.Components[definition];
        var inputs = def.CustomProperties.Values.Where(p => p.Kind == "Input")
            .Select(p => new NamedValue(p.Name, p.Default is null ? FormulaValue.NewBlank() : Eval(CanvasSource.Strip(p.Default))));
        Engine.UpdateVariable(def.Name, FormulaValue.NewRecordFromFields(inputs));
        return Check(formula);
    }

    /// <summary>Evaluates a property of a control inside the component, as seen through the given instance.</summary>
    public FormulaValue Inside(string instance, string control, string property)
    {
        Enter(instance);
        var c = Library.Controls[control];
        if (!c.InComponent || c.Owner != Definition(instances[instance]).Name)
            throw new InvalidOperationException($"{control} isn't part of {instances[instance].ComponentName}");
        return Eval(CanvasSource.Strip(c.Properties[property]));
    }

    /// <summary>A tap on a control inside the component instance (runs its OnSelect).</summary>
    public void Tap(string instance, string control) => Inside(instance, control, "OnSelect");

    private void Fire(string definition, string evt)
    {
        if (!current.TryGetValue(definition, out var instance))
            throw new InvalidOperationException($"{definition}.{evt}() raised outside any instance");
        Calls.Add($"{instance}.{evt}");
        var inst = instances[instance];
        var handler = inst.Properties.TryGetValue(evt, out var f) ? f : Definition(inst).CustomProperties[evt].Default;
        if (handler is not null) Eval(CanvasSource.Strip(handler)); // the handler runs in the app, not in the component
    }

    // ---- data --------------------------------------------------------------------------------------------------

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

    public void SetThisItem(RecordValue row) => Engine.UpdateVariable("ThisItem", row);

    public void SetControl(string name, params (string Property, FormulaValue Value)[] props) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(props.Select(p => new NamedValue(p.Property, p.Value))));

    private void Enum(string name, params string[] members) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(members.Select(m => new NamedValue(m, FormulaValue.New(m)))));

    private sealed class FixedClock(DateTime day) : IClockService
    {
        public DateTime UtcNow { get; set; } = DateTime.SpecifyKind(day.Date.AddHours(9), DateTimeKind.Utc);
    }

    private sealed class EventFunction(string name, Action fire) : ReflectionFunction(name, FormulaType.Boolean)
    {
        public BooleanValue Execute() { fire(); return FormulaValue.New(true); }
    }

    private sealed class NotifyFunction(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message, StringValue type) { calls.Add($"Notify({type.Value}): {message.Value}"); return FormulaValue.New(true); }
    }

    private sealed class BackFunction(List<string> calls) : ReflectionFunction("Back", FormulaType.Boolean)
    {
        public BooleanValue Execute() { calls.Add("Back()"); return FormulaValue.New(true); }
    }

    private sealed class CopyFunction(List<string> calls) : ReflectionFunction("Copy", FormulaType.Boolean, FormulaType.String)
    {
        public BooleanValue Execute(StringValue text) { calls.Add($"Copy: {text.Value}"); return FormulaValue.New(true); }
    }
}
