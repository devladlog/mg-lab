using Microsoft.PowerFx;
using Microsoft.PowerFx.Core;
using Microsoft.PowerFx.Core.Utils;
using Microsoft.PowerFx.Types;

namespace EquipmentDesk.Canvas.Tests;

/// <summary>
/// Runs the app's formulas on Microsoft's open-source Power Fx interpreter, against in-memory tables shaped like the
/// Dataverse tables (same display names and local choices). Canvas-only functions (Navigate, Back, Notify) are stubs
/// that record their calls. This tests formula LOGIC; it can't test delegation, which only the real connector does.
/// </summary>
public sealed class Harness
{
    public RecalcEngine Engine { get; }
    public OptionSet Status { get; }
    public OptionSet Category { get; }
    public RecordType EquipmentType { get; }
    public RecordType LoanType { get; }
    // The data sources live in a host symbol table (like connector tables in a real app), so a test can swap one
    // for a table that refuses writes.
    private readonly SymbolTable dataSymbols = new();
    private readonly ReadOnlySymbolValues dataValues;
    private readonly ISymbolSlot equipmentSlot, loansSlot;
    private readonly RuntimeConfig runtime;
    public TableValue Equipment => (TableValue)dataValues.Get(equipmentSlot);
    public TableValue Loans => (TableValue)dataValues.Get(loansSlot);
    public List<string> Calls { get; } = new();
    private static readonly ParserOptions Behavior = new() { AllowsSideEffects = true };

    public Harness(CanvasSource source)
    {
        var config = new PowerFxConfig();
        var symbols = new SymbolTable();
        symbols.EnableMutationFunctions(); // Collect, Patch, Remove on in-memory tables
        config.SymbolTable = symbols;
        config.EnableSetFunction();
        config.EnableRegExFunctions(TimeSpan.FromSeconds(1), 50); // IsMatch + Match.Email

        // Local choices are named "<Column> (<Table plural>)" in canvas apps, e.g. 'Status (Equipment)'.
        Status = new OptionSet("Status (Equipment)", DisplayNameUtility.MakeUnique(new Dictionary<string, string>
            { ["Available"] = "Available", ["OnLoan"] = "On loan", ["InRepair"] = "In repair", ["Retired"] = "Retired" }));
        Category = new OptionSet("Category (Equipment)", DisplayNameUtility.MakeUnique(new Dictionary<string, string>
            { ["Laptop"] = "Laptop", ["Monitor"] = "Monitor", ["Phone"] = "Phone", ["Accessory"] = "Accessory" }));
        config.AddOptionSet(Status);
        config.AddOptionSet(Category);

        config.AddFunction(new NotifyFunction(Calls));
        config.AddFunction(new NavigateFunction(Calls));
        config.AddFunction(new BackFunction(Calls));

        Engine = new RecalcEngine(config);

        // Logical names as in Dataverse, display names as the maker sees them in Studio.
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
            .Add("contoso_returnedon", FormulaType.Date, "Returned on");

        var equipment = FormulaValue.NewTable(EquipmentType,
            Device("CT-0042", "Laptop 14", "Laptop", "Available"),
            Device("CT-0043", "Laptop 14", "Laptop", "OnLoan"),
            Device("CT-0107", "Monitor 27", "Monitor", "Available"),
            Device("CT-0311", "Phone", "Phone", "InRepair"),
            Device("CT-0400", "Dock", "Accessory", "Retired"),
            Device("CT-0108", "Monitor 24", "Monitor", "Available"));
        var mutable = new SymbolProperties { CanMutate = true };
        equipmentSlot = dataSymbols.AddVariable("Equipment", EquipmentType.ToTable(), mutable);
        loansSlot = dataSymbols.AddVariable("Loans", LoanType.ToTable(), mutable);
        dataValues = dataSymbols.CreateValues();
        dataValues.Set(equipmentSlot, equipment);
        dataValues.Set(loansSlot, FormulaValue.NewTable(LoanType));
        runtime = new RuntimeConfig(dataValues);

        // Canvas enums and screens the formulas refer to.
        Enum("NotificationType", "Success", "Error", "Warning", "Information");
        Enum("ScreenTransition", "None", "Cover", "UnCover", "Fade");
        Enum("DisplayMode", "Edit", "View", "Disabled");
        Enum("FontWeight", "Normal", "Semibold", "Bold");
        Engine.UpdateVariable("BrowseScreen", FormulaValue.New("BrowseScreen"));
        Engine.UpdateVariable("LendScreen", FormulaValue.New("LendScreen"));

        foreach (var (name, expr) in source.NamedFormulas()) Engine.SetFormula(name, expr, null);

        // Default control state, as when the app starts.
        SetControl("txtSearch", ("Text", FormulaValue.New("")));
        SetControl("tglAvailableOnly", ("Value", FormulaValue.New(true)));
        SelectDevice("CT-0042");
        SetControl("txtEmail", ("Text", FormulaValue.New("")));
        SetControl("dpLoan", ("SelectedDate", FormulaValue.NewDateOnly(new DateTime(2026, 11, 21))));
        SetControl("dpDue", ("SelectedDate", FormulaValue.NewDateOnly(new DateTime(2026, 12, 5))));
    }

    public RecordValue Device(string tag, string name, string category, string status) =>
        FormulaValue.NewRecordFromFields(EquipmentType,
            new NamedValue("contoso_name", FormulaValue.New(name)),
            new NamedValue("contoso_assettag", FormulaValue.New(tag)),
            new NamedValue("contoso_category", Option(Category, category)),
            new NamedValue("contoso_status", Option(Status, status)));

    public static OptionSetValue Option(OptionSet set, string logicalName) =>
        set.TryGetValue(new DName(logicalName), out var v) ? v : throw new ArgumentException(logicalName);

    public void SetControl(string name, params (string Property, FormulaValue Value)[] props) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(props.Select(p => new NamedValue(p.Property, p.Value))));

    /// <summary>The gallery's Selected record is a row of the Equipment table (as when the user taps it).</summary>
    public void SelectDevice(string tag)
    {
        var row = Equipment.Rows.Select(r => r.Value).First(r => ((StringValue)r.GetField("contoso_assettag")).Value == tag);
        SetControl("galEquipment", ("Selected", row));
    }

    public void SelectRecord(RecordValue record) => SetControl("galEquipment", ("Selected", record));

    /// <summary>From now on every write to the table fails with this message (e.g. no Write privilege).</summary>
    public void MakeReadOnly(string table, string message)
    {
        var slot = table == "Loans" ? loansSlot : equipmentSlot;
        dataValues.Set(slot, new ReadOnlyTable((TableValue)dataValues.Get(slot), message));
    }

    public FormulaValue Eval(string formula)
    {
        var result = Engine.EvalAsync(formula, CancellationToken.None, Behavior, dataSymbols, runtime).GetAwaiter().GetResult();
        return result is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : result;
    }

    public CheckResult Check(string formula) => Engine.Check(formula, Behavior, dataSymbols);

    public IEnumerable<string> Column(TableValue table, string field) =>
        table.Rows.Select(r => r.Value.GetField(field) switch
        {
            StringValue s => s.Value,
            OptionSetValue o => o.DisplayName, // what the user sees: "On loan"
            var v => v.ToObject()?.ToString() ?? "",
        });

    private void Enum(string name, params string[] members) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(members.Select(m => new NamedValue(m, FormulaValue.New(m)))));

    private sealed class NotifyFunction(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message, StringValue type) { calls.Add($"Notify({type.Value}): {message.Value}"); return FormulaValue.New(true); }
    }

    private sealed class NavigateFunction(List<string> calls) : ReflectionFunction("Navigate", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue screen, StringValue transition) { calls.Add($"Navigate({screen.Value}, {transition.Value})"); return FormulaValue.New(true); }
    }

    private sealed class BackFunction(List<string> calls) : ReflectionFunction("Back", FormulaType.Boolean)
    {
        public BooleanValue Execute() { calls.Add("Back()"); return FormulaValue.New(true); }
    }
}
