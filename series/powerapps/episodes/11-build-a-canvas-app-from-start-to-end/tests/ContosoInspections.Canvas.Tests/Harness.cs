using System.Globalization;
using System.Text.Json;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Core;
using Microsoft.PowerFx.Core.Utils;
using Microsoft.PowerFx.Functions;
using Microsoft.PowerFx.Types;

namespace ContosoInspections.Canvas.Tests;

/// <summary>
/// Runs the Contoso Inspections app formulas (App.Formulas named formulas and UDFs, and every control property) on Microsoft's
/// open-source Power Fx interpreter (1.8.1). The Dataverse tables are NOT hand-written here: their record types, choice sets and
/// lookups are built from src/schema/contosoinspections.schema.json, the same file the provisioning script uses, so the app can't
/// compile against a column the schema doesn't have. Rows live in mutable in-memory tables (Collect and Patch work); a new row
/// gets a GUID the way Dataverse assigns one. The clock is fixed: Today() = Monday 30 November 2026.
///
/// What is stubbed (the interpreter has none of these): Notify, Back, Navigate, ShowHostInfo, User(). Calls are recorded in Calls.
/// The Connection and Host records and the Camera, Dropdown, TextInput and DatePicker controls are plain records set by the test.
/// This cannot prove delegation, security roles, offline sync or the camera: see README, "What the tests do not prove".
/// </summary>
public sealed class Harness
{
    public static readonly DateTime DefaultToday = new(2026, 11, 30);
    /// <summary>What a screen name evaluates to here: Name (what Navigate receives) plus the Width, Height and Size formulas read.</summary>
    public static readonly RecordType ScreenType = RecordType.Empty().Add("Name", FormulaType.String).Add("Width", FormulaType.Number)
        .Add("Height", FormulaType.Number).Add("Size", FormulaType.Number);
    public static readonly string[] ScreenNames = ["InspectionsScreen", "InspectionScreen", "NewInspectionScreen", "FindingScreen"];

    public CanvasSource App { get; }
    public JsonElement Schema { get; }
    public RecalcEngine Engine { get; }
    public List<string> Calls { get; } = new();
    public DefinitionsCheckResult FunctionsResult { get; private set; } = null!;
    public Dictionary<string, RecordType> Types { get; } = new();
    public Dictionary<string, OptionSet> OptionSets { get; } = new();
    public string UserEmail { get; set; } = "alex.demo@contoso.com";

    public TableValue Sites => Table("cin_site");
    public TableValue Inspectors => Table("cin_inspector");
    public TableValue Inspections => Table("cin_inspection");
    public TableValue Findings => Table("cin_finding");

    private readonly SymbolTable dataSymbols = new();
    private readonly ReadOnlySymbolValues dataValues;
    private readonly Dictionary<string, ISymbolSlot> slots = new();
    private readonly RuntimeConfig runtime;
    private readonly FixedClock clock = new(DefaultToday);
    private static readonly ParserOptions Behavior = new() { AllowsSideEffects = true };

    public static JsonElement LoadSchema() =>
        JsonDocument.Parse(File.ReadAllText(Path.Combine(CanvasSource.EpisodeDir, "src", "schema", "contosoinspections.schema.json"))).RootElement;

    public Harness(CanvasSource app)
    {
        App = app;
        Schema = LoadSchema();

        var config = new PowerFxConfig();
        var symbols = new SymbolTable();
        symbols.EnableMutationFunctions();
        config.SymbolTable = symbols;
        config.EnableSetFunction();

        BuildTypes(config);
        config.AddFunction(new NotifyFunction(Calls));
        config.AddFunction(new BackFunction(Calls));
        config.AddFunction(new NavigateFunction(Calls));
        config.AddFunction(new ShowHostInfoFunction(Calls));
        config.AddFunction(new UserFunction(() => UserEmail));

        Engine = new RecalcEngine(config);

        var mutable = new SymbolProperties { CanMutate = true };
        foreach (var t in Schema.GetProperty("tables").EnumerateArray())
        {
            var logical = Logical(t.GetProperty("schemaName").GetString()!);
            slots[logical] = dataSymbols.AddVariable(t.GetProperty("pluralName").GetString()!, Types[logical].ToTable(), mutable);
        }
        dataValues = dataSymbols.CreateValues();
        SeedData();

        runtime = new RuntimeConfig(dataValues);
        runtime.AddService<IClockService>(clock);
        runtime.AddService(TimeZoneInfo.Utc);
        runtime.SetCulture(new CultureInfo("en-GB"));

        Enum("NotificationType", "Success", "Error", "Warning", "Information");
        Enum("FontWeight", "Normal", "Semibold", "Bold");
        Enum("DisplayMode", "Edit", "View", "Disabled");
        Enum("TextRole", "Default", "Heading1", "Heading2", "Heading3", "Heading4");
        Enum("TextMode", "SingleLine", "MultiLine", "Password");
        Enum("ScreenTransition", "None", "Cover", "UnCover", "Fade");
        Enum("Icon", "ChevronLeft", "ChevronRight", "Cancel", "Check", "Globe", "GlobeWarning", "GlobeChangesPending",
            "GlobeError", "GlobeRefresh", "GlobeNotConnected");
        Enum("ConnectionSync", "Connected", "ConnectedWithWarning", "ConnectedPendingUpsync", "ConnectedError", "ConnectedRefresh",
            "NotConnected", "NotConnectedWithWarning", "NotConnectedPendingUpsync", "NotConnectedSyncError");
        Enum("HostInfo", "OfflineSync");
        Enum("Live", "Off", "Polite", "Assertive");
        Enum("LayoutDirection", "Horizontal", "Vertical");
        // Learn (create responsive layouts): Small = 1 (phone), Medium = 2, Large = 3, ExtraLarge = 4.
        Engine.UpdateVariable("ScreenSize", FormulaValue.NewRecordFromFields(
            new NamedValue("Small", FormulaValue.New(1m)), new NamedValue("Medium", FormulaValue.New(2m)),
            new NamedValue("Large", FormulaValue.New(3m)), new NamedValue("ExtraLarge", FormulaValue.New(4m))));

        // Screens are records with a Name (what Navigate receives) plus Width/Height/Size (what formulas read).
        foreach (var s in ScreenNames) SetScreen(s, 780, 1688, 1);

        Engine.UpdateVariable("statusFilter", FormulaValue.NewBlank(OptionSets["cin_inspection.cin_status"].FormulaType));
        Engine.UpdateVariable("selectedInspection", FormulaValue.NewBlank(Types["cin_inspection"]));
        Engine.UpdateVariable("selectedFinding", FormulaValue.NewBlank(Types["cin_finding"]));
        Engine.UpdateVariable("findingPhoto", FormulaValue.NewBlank(FormulaType.String));

        SetConnection(true, "Connected");
        SetHost(offlineEnabled: true);
        SetGenericLayoutRecords();
        SetControls();
        LoadFormulas();
        SetDevice(780, 1688);
    }

    // ---- schema -> types ------------------------------------------------------------------------------------------------

    public static string Logical(string schemaName) => schemaName.ToLowerInvariant();

    private static string Identifier(string label) => new string(label.Where(char.IsLetterOrDigit).ToArray());

    private void BuildTypes(PowerFxConfig config)
    {
        var rels = Schema.GetProperty("relationships").EnumerateArray().ToList();
        foreach (var t in Schema.GetProperty("tables").EnumerateArray())
        {
            var logical = Logical(t.GetProperty("schemaName").GetString()!);
            var plural = t.GetProperty("pluralName").GetString()!;
            var rt = RecordType.Empty().Add($"{logical}id", FormulaType.Guid, t.GetProperty("displayName").GetString()!);
            var primary = t.GetProperty("primaryName");
            rt = rt.Add(Logical(primary.GetProperty("schemaName").GetString()!), FormulaType.String, primary.GetProperty("displayName").GetString()!);
            foreach (var c in t.GetProperty("columns").EnumerateArray())
            {
                var colLogical = Logical(c.GetProperty("schemaName").GetString()!);
                var display = c.GetProperty("displayName").GetString()!;
                FormulaType ft;
                switch (c.GetProperty("type").GetString())
                {
                    case "string" or "memo": ft = FormulaType.String; break;
                    case "date": ft = FormulaType.Date; break;
                    case "boolean": ft = FormulaType.Boolean; break;
                    case "image": ft = RecordType.Empty().Add("Full", FormulaType.String).Add("Value", FormulaType.String); break;
                    case "choice":
                        var names = c.GetProperty("options").EnumerateArray().Select(o => o.GetString()!).ToList();
                        var os = new OptionSet($"{display} ({plural})", DisplayNameUtility.MakeUnique(names.ToDictionary(Identifier, n => n)));
                        config.AddOptionSet(os);
                        OptionSets[$"{logical}.{colLogical}"] = os;
                        ft = os.FormulaType;
                        break;
                    default: throw new NotSupportedException(c.GetProperty("type").GetString());
                }
                rt = rt.Add(colLogical, ft, display);
            }
            foreach (var r in rels.Where(r => r.GetProperty("referencing").GetString() == t.GetProperty("schemaName").GetString()))
            {
                var look = r.GetProperty("lookup");
                rt = rt.Add(Logical(look.GetProperty("schemaName").GetString()!), Types[Logical(r.GetProperty("referenced").GetString()!)],
                    look.GetProperty("displayName").GetString()!);
            }
            Types[logical] = rt;
        }
    }

    public TableValue Table(string logical) => (TableValue)dataValues.Get(slots[logical]);

    public static Guid Id(int n) => new($"00000000-0000-0000-0000-{n:D12}");

    public OptionSetValue Option(string column, string label)
    {
        var os = OptionSets[column];
        return os.TryGetValue(new DName(Identifier(label)), out var v) ? v : throw new ArgumentException($"{column}: {label}");
    }

    private RecordValue Row(string logical, params (string Field, FormulaValue Value)[] values)
    {
        var rt = Types[logical];
        var given = values.ToDictionary(v => v.Field, v => v.Value);
        return FormulaValue.NewRecordFromFields(rt, rt.GetFieldTypes().Select(f =>
            new NamedValue(f.Name, given.TryGetValue(f.Name, out var v) ? v : FormulaValue.NewBlank(f.Type))));
    }

    private static FormulaValue S(string s) => FormulaValue.New(s);
    private static FormulaValue D(int y, int m, int d) => FormulaValue.NewDateOnly(new DateTime(y, m, d));

    private void SeedData()
    {
        var sampleSites = Schema.GetProperty("sampleData").GetProperty("sites").EnumerateArray().ToList();
        var siteRows = sampleSites.Select((s, i) => Row("cin_site",
            ("cin_siteid", FormulaValue.New(Id(100 + i))), ("cin_name", S(s.GetProperty("name").GetString()!)),
            ("cin_sitecode", S(s.GetProperty("code").GetString()!)), ("cin_city", S(s.GetProperty("city").GetString()!)),
            ("cin_riskrating", Option("cin_site.cin_riskrating", s.GetProperty("risk").GetString()!)))).ToList();
        var inspectorRows = Schema.GetProperty("sampleData").GetProperty("inspectors").EnumerateArray().Select((s, i) => Row("cin_inspector",
            ("cin_inspectorid", FormulaValue.New(Id(200 + i))), ("cin_name", S(s.GetProperty("name").GetString()!)),
            ("cin_workemail", S(s.GetProperty("defaultEmail").GetString()!)), ("cin_region", S(s.GetProperty("region").GetString()!)),
            ("cin_certified", FormulaValue.New(s.GetProperty("certified").GetBoolean())))).ToList();

        var alex = inspectorRows[0];
        // Alex's own rows only: the role gives Basic scope, so Dataverse (here: the seed) never returns anyone else's.
        var i1 = Row("cin_inspection", ("cin_inspectionid", FormulaValue.New(Id(301))), ("cin_reference", S("CWN-01-20261125-AD-001")),
            ("cin_siteid", siteRows[0]), ("cin_inspectorid", alex), ("cin_inspectiondate", D(2026, 11, 25)),
            ("cin_status", Option("cin_inspection.cin_status", "Submitted")), ("cin_result", Option("cin_inspection.cin_result", "Pass")),
            ("cin_summary", S("All clear.")));
        var i2 = Row("cin_inspection", ("cin_inspectionid", FormulaValue.New(Id(302))), ("cin_reference", S("CPE-02-20261127-AD-001")),
            ("cin_siteid", siteRows[1]), ("cin_inspectorid", alex), ("cin_inspectiondate", D(2026, 11, 27)),
            ("cin_status", Option("cin_inspection.cin_status", "Draft")));
        var i3 = Row("cin_inspection", ("cin_inspectionid", FormulaValue.New(Id(303))), ("cin_reference", S("CDS-03-20261130-AD-001")),
            ("cin_siteid", siteRows[2]), ("cin_inspectorid", alex), ("cin_inspectiondate", D(2026, 11, 30)),
            ("cin_status", Option("cin_inspection.cin_status", "Draft")));

        RecordValue Finding(int n, string title, RecordValue inspection, string severity, string category, DateTime? resolveBy, bool resolved) =>
            Row("cin_finding", ("cin_findingid", FormulaValue.New(Id(n))), ("cin_title", S(title)), ("cin_inspectionid", inspection),
                ("cin_severity", Option("cin_finding.cin_severity", severity)), ("cin_category", Option("cin_finding.cin_category", category)),
                ("cin_resolved", FormulaValue.New(resolved)),
                ("cin_resolveby", resolveBy is { } r ? FormulaValue.NewDateOnly(r) : FormulaValue.NewBlank(FormulaType.Date)));

        var findings = new[]
        {
            Finding(401, "Loose handrail", i1, "Minor", "Safety", new(2026, 12, 25), true),
            Finding(402, "Fire door wedged open", i2, "Major", "Safety", new(2026, 12, 7), false),
            Finding(403, "Extinguisher tag out of date", i2, "Minor", "Documentation", new(2026, 11, 28), false), // overdue
            Finding(404, "Pallets blocking an aisle", i2, "Observation", "Housekeeping", null, true),
        };

        Set("cin_site", siteRows, "cin_siteid");
        Set("cin_inspector", inspectorRows, "cin_inspectorid");
        Set("cin_inspection", new[] { i1, i2, i3 }, "cin_inspectionid");
        Set("cin_finding", findings, "cin_findingid");
    }

    private void Set(string logical, IEnumerable<RecordValue> rows, string key) =>
        dataValues.Set(slots[logical], new DataverseTable(Types[logical], rows, key));

    // ---- the device -----------------------------------------------------------------------------------------------------

    public decimal ScreenWidth { get; private set; }
    public decimal ScreenHeight { get; private set; }

    /// <summary>
    /// Sets App.Width/App.Height as the device reports them, then evaluates each screen's own Width and Height formulas and its
    /// Size. Learn: "The screen's Size property is calculated by comparing the screen's Width property to the values in the app's
    /// SizeBreakpoints property." A width that reaches a breakpoint counts as the larger size; Learn doesn't say which side the
    /// boundary falls on, so tests don't use exact breakpoint widths.
    /// </summary>
    public void SetDevice(decimal appWidth, decimal appHeight)
    {
        var breakpoints = (TableValue)Eval(CanvasSource.Strip(App.AppProperties["SizeBreakpoints"]));
        Engine.UpdateVariable("App", FormulaValue.NewRecordFromFields(
            new NamedValue("Width", FormulaValue.New(appWidth)),
            new NamedValue("Height", FormulaValue.New(appHeight)),
            new NamedValue("DesignWidth", FormulaValue.New(640m)),   // phone portrait design size (Learn's example)
            new NamedValue("DesignHeight", FormulaValue.New(1136m)),
            new NamedValue("MinScreenWidth", Eval(CanvasSource.Strip(App.AppProperties["MinScreenWidth"]))),
            new NamedValue("MinScreenHeight", Eval(CanvasSource.Strip(App.AppProperties["MinScreenHeight"]))),
            new NamedValue("SizeBreakpoints", breakpoints)));
        var bps = breakpoints.Rows.Select(r => r.Value.GetField("Value") switch { DecimalValue d => d.Value, NumberValue n => (decimal)n.Value, _ => 0m }).ToList();
        foreach (var screen in ScreenNames)
        {
            var props = App.ScreenProperties[screen];
            ScreenWidth = Number(CanvasSource.Strip(props["Width"]));
            ScreenHeight = Number(CanvasSource.Strip(props["Height"]));
            SetScreen(screen, ScreenWidth, ScreenHeight, 1 + bps.Count(bp => ScreenWidth >= bp));
        }
    }

    public int SizeOf(string screen) => (int)Number($"{screen}.Size");

    private void SetScreen(string name, decimal w, decimal h, int size) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(ScreenType,
            new NamedValue("Name", S(name)), new NamedValue("Width", FormulaValue.New((double)w)),
            new NamedValue("Height", FormulaValue.New((double)h)), new NamedValue("Size", FormulaValue.New((double)size))));

    /// <summary>The Connection signal (Learn: Connected, Metered, Sync).</summary>
    public void SetConnection(bool connected, string sync, bool metered = false) =>
        Engine.UpdateVariable("Connection", FormulaValue.NewRecordFromFields(
            new NamedValue("Connected", FormulaValue.New(connected)),
            new NamedValue("Metered", FormulaValue.New(metered)),
            new NamedValue("Sync", S(sync))));

    /// <summary>Host.OfflineEnabled: true in a player that supports offline (Power Apps mobile), false in a browser.</summary>
    public void SetHost(bool offlineEnabled) =>
        Engine.UpdateVariable("Host", FormulaValue.NewRecordFromFields(new NamedValue("OfflineEnabled", FormulaValue.New(offlineEnabled))));

    // ---- controls (plain records the test sets) ---------------------------------------------------------------------------

    /// <summary>The control the formula runs in (Self): only the camera's Photo matters to the behavior tests.</summary>
    public void SetSelf(string photo = "", string text = "", bool visible = true) =>
        Engine.UpdateVariable("SelfRec", FormulaValue.NewRecordFromFields(
            new NamedValue("Visible", FormulaValue.New(visible)), new NamedValue("Text", S(text)), new NamedValue("Photo", S(photo)),
            new NamedValue("X", FormulaValue.New(0m)), new NamedValue("Y", FormulaValue.New(0m)),
            new NamedValue("Width", FormulaValue.New(0m)), new NamedValue("Height", FormulaValue.New(0m))));

    private void SetGenericLayoutRecords()
    {
        Engine.UpdateVariable("ParentRec", FormulaValue.NewRecordFromFields(
            new NamedValue("Width", FormulaValue.New(780m)), new NamedValue("Height", FormulaValue.New(1688m)),
            new NamedValue("TemplateWidth", FormulaValue.New(780m)), new NamedValue("TemplateHeight", FormulaValue.New(128m))));
        Engine.UpdateVariable("SelfRec", FormulaValue.NewRecordFromFields(
            new NamedValue("Visible", FormulaValue.New(true)), new NamedValue("Text", S("")), new NamedValue("Photo", S("")),
            new NamedValue("X", FormulaValue.New(0m)), new NamedValue("Y", FormulaValue.New(0m)),
            new NamedValue("Width", FormulaValue.New(0m)), new NamedValue("Height", FormulaValue.New(0m))));
    }

    private void SetControls()
    {
        SetControl("txtSearch", ("Text", S("")));
        SetControl("txtSummary", ("Text", S("")));
        SetControl("txtFindingTitle", ("Text", S("")));
        SetControl("txtFindingDetails", ("Text", S("")));
        SetControl("camFinding", ("Photo", S("")));
        SetControl("lblOffline", ("Visible", FormulaValue.New(false)), ("Height", FormulaValue.New(0m)));
        PickText("drpResult", "Pass");
        PickText("drpSeverity", "Observation");
        PickText("drpCategory", "Safety");
        SetControl("drpSite", ("Selected", Sites.Rows.First().Value));
        SetControl("dpInspectionDate", ("SelectedDate", D(2026, 11, 30)));
    }

    /// <summary>A dropdown over a string array: Selected is a record with Value.</summary>
    public void PickText(string control, string value) =>
        SetControl(control, ("Selected", FormulaValue.NewRecordFromFields(new NamedValue("Value", S(value)))));

    public void SetControl(string name, params (string Property, FormulaValue Value)[] props) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(props.Select(p => new NamedValue(p.Property, p.Value))));

    public void SetVariable(string name, FormulaValue value) => Engine.UpdateVariable(name, value);
    public void SetThisItem(RecordValue row) => Engine.UpdateVariable("ThisItem", row);

    public RecordValue InspectionRow(string reference) =>
        Inspections.Rows.Select(r => r.Value).First(r => Field(r, "cin_reference") == reference);

    public RecordValue FindingRow(string title) =>
        Findings.Rows.Select(r => r.Value).First(r => Field(r, "cin_title") == title);

    public RecordValue SiteRow(string code) => Sites.Rows.Select(r => r.Value).First(r => Field(r, "cin_sitecode") == code);

    public void Select(string reference) => Eval($"Set(selectedInspection, LookUp(Inspections, Reference = \"{reference}\"))");
    public void SelectFinding(string title) => Eval($"Set(selectedFinding, LookUp(Findings, Title = \"{title}\"))");

    public void MakeReadOnly(string logical, string message) =>
        dataValues.Set(slots[logical], new ReadOnlyTable(Table(logical), message));

    // ---- formulas -------------------------------------------------------------------------------------------------------

    private void LoadFormulas()
    {
        Recalc();
        var udfs = string.Join("\n", App.Definitions().Where(d => d.Kind != CanvasSource.DefinitionKind.NamedFormula).Select(d => d.Text + ";"));
        FunctionsResult = Engine.AddUserDefinedFunction(udfs, CultureInfo.InvariantCulture,
            ReadOnlySymbolTable.Compose(Engine.EngineSymbols, dataSymbols), allowSideEffects: true);
    }

    /// <summary>Evaluates the App.Formulas named formulas in dependency order. Power Apps recalculates them on its own; tests call
    /// this after a write (Run does it for them).</summary>
    public void Recalc()
    {
        var pending = App.Definitions().Where(d => d.Kind == CanvasSource.DefinitionKind.NamedFormula).ToList();
        while (pending.Count > 0)
        {
            var done = pending.Where(d => Check(d.Expression).IsSuccess).ToList();
            if (done.Count == 0) throw new InvalidOperationException("named formulas that don't bind: " + string.Join(", ", pending.Select(p => p.Name)));
            foreach (var d in done) Engine.UpdateVariable(d.Name, Eval(d.Expression));
            pending = pending.Except(done).ToList();
        }
    }

    /// <summary>
    /// The open-source engine has no Parent or Self (Power Apps supplies them), so Parent.X and Self.X are read from two plain
    /// records named ParentRec and SelfRec. That rewrite is the only liberty taken with the source formulas.
    /// </summary>
    public static string Rewrite(string formula) =>
        System.Text.RegularExpressions.Regex.Replace(formula, @"\b(Parent|Self)\.", m => $"{m.Groups[1].Value}Rec.");

    public FormulaValue Eval(string formula)
    {
        formula = Rewrite(formula);
        var result = Engine.EvalAsync(formula, CancellationToken.None, Behavior, dataSymbols, runtime).GetAwaiter().GetResult();
        return result is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : result;
    }

    public CheckResult Check(string formula) => Engine.Check(Rewrite(formula), Behavior, dataSymbols);

    public string Text(string formula) => Eval(formula) switch { StringValue s => s.Value, BlankValue => "", var v => v.ToObject()?.ToString() ?? "" };
    public bool Bool(string formula) => Eval(formula) switch { BooleanValue b => b.Value, BlankValue => false, var v => throw new InvalidCastException(v.GetType().Name) };
    public decimal Number(string formula) => Eval(formula) switch { DecimalValue d => d.Value, NumberValue n => (decimal)n.Value, var v => throw new InvalidCastException(v.GetType().Name) };
    public string DateText(string formula) => Eval(formula) is DateValue d ? d.GetConvertedValue(TimeZoneInfo.Utc).ToString("yyyy-MM-dd") : throw new InvalidCastException();

    /// <summary>Runs an app control property (OnSelect and the like), then recalculates the named formulas.</summary>
    public FormulaValue Run(string control, string property)
    {
        var result = Eval(App.Formula(control, property));
        Recalc();
        return result;
    }

    /// <summary>Calls a UDF or any expression that writes, then recalculates.</summary>
    public FormulaValue Do(string formula)
    {
        var result = Eval(formula);
        Recalc();
        return result;
    }

    public static string Field(RecordValue r, string name) => r.GetField(name) switch
    {
        StringValue s => s.Value,
        BlankValue => "",
        OptionSetValue o => o.Option,
        DateValue d => d.GetConvertedValue(TimeZoneInfo.Utc).ToString("yyyy-MM-dd"),
        BooleanValue b => b.Value ? "true" : "false",
        var v => v.ToObject()?.ToString() ?? "",
    };

    public int Count(string logical) => Table(logical).Rows.Count();

    private void Enum(string name, params string[] members) =>
        Engine.UpdateVariable(name, FormulaValue.NewRecordFromFields(members.Select(m => new NamedValue(m, S(m)))));

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

    private sealed class NavigateFunction(List<string> calls) : ReflectionFunction("Navigate", FormulaType.Boolean, ScreenType, FormulaType.String)
    {
        public BooleanValue Execute(RecordValue screen, StringValue transition)
        {
            calls.Add($"Navigate({((StringValue)screen.GetField("Name")).Value}, {transition.Value})");
            return FormulaValue.New(true);
        }
    }

    private sealed class ShowHostInfoFunction(List<string> calls) : ReflectionFunction("ShowHostInfo", FormulaType.Boolean, FormulaType.String)
    {
        public BooleanValue Execute(StringValue info) { calls.Add($"ShowHostInfo({info.Value})"); return FormulaValue.New(true); }
    }

    private sealed class UserFunction(Func<string> email) : ReflectionFunction("User", RecordType.Empty().Add("Email", FormulaType.String).Add("FullName", FormulaType.String))
    {
        public RecordValue Execute() => FormulaValue.NewRecordFromFields(new NamedValue("Email", S(email())), new NamedValue("FullName", S("Alex Demo")));
    }
}

/// <summary>
/// An in-memory table that behaves like a Dataverse table for Collect and Patch: it assigns the primary key on append (Collect
/// doesn't set one) and Patch replaces the matching row (found by reference, else by key) with the base plus the changes.
/// </summary>
public sealed class DataverseTable : TableValue
{
    private readonly List<RecordValue> rows;
    private readonly RecordType recordType;
    private readonly string key;

    public DataverseTable(RecordType recordType, IEnumerable<RecordValue> seed, string key) : base(recordType.ToTable())
    {
        this.recordType = recordType;
        this.key = key;
        rows = seed.ToList();
    }

    public override IEnumerable<DValue<RecordValue>> Rows => rows.ToList().Select(DValue<RecordValue>.Of);

    private RecordValue Full(Func<string, FormulaValue?> value) =>
        FormulaValue.NewRecordFromFields(recordType, recordType.GetFieldTypes().Select(f =>
            new NamedValue(f.Name, value(f.Name) ?? FormulaValue.NewBlank(f.Type))));

    public override Task<DValue<RecordValue>> AppendAsync(RecordValue record, CancellationToken cancellationToken)
    {
        var given = record.Fields.ToDictionary(f => f.Name, f => f.Value);
        given[key] = FormulaValue.New(Guid.NewGuid());
        var full = Full(n => given.GetValueOrDefault(n));
        rows.Add(full);
        return Task.FromResult(DValue<RecordValue>.Of(full));
    }

    protected override Task<DValue<RecordValue>> PatchCoreAsync(RecordValue baseRecord, RecordValue changeRecord, CancellationToken cancellationToken)
    {
        var at = rows.FindIndex(r => ReferenceEquals(r, baseRecord));
        if (at < 0) at = rows.FindIndex(r => r.GetField(key).ToObject()?.ToString() == baseRecord.GetField(key).ToObject()?.ToString());
        if (at < 0) return Task.FromResult(DValue<RecordValue>.Of(FormulaValue.NewError(new ExpressionError { Message = "The record isn't in the table", Kind = ErrorKind.NotFound })));
        var changed = changeRecord.Fields.ToDictionary(f => f.Name, f => f.Value);
        var merged = Full(n => changed.TryGetValue(n, out var v) ? v : rows[at].GetField(n));
        rows[at] = merged;
        return Task.FromResult(DValue<RecordValue>.Of(merged));
    }
}
