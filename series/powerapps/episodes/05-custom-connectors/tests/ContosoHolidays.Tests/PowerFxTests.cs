using System.Globalization;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Connectors;
using Microsoft.PowerFx.Functions;
using Microsoft.PowerFx.Types;
using Xunit;
using YamlDotNet.RepresentationModel;

namespace ContosoHolidays.Tests;

/// <summary>
/// The app side: Microsoft's open-source Power Fx connector library (Microsoft.PowerFx.Connectors) turns the OpenAPI
/// definition into Power Fx functions, the same way a canvas app sees ContosoHolidays.GetDaysOff. Calls go through a
/// stand-in for the platform (PlatformHandler: host + path, script.csx for GetDaysOff) to the recorded holiday source.
/// The named formulas and working-day UDFs come straight from src/app/Src/App.pa.yaml. Today() is Mon 30 Nov 2026.
/// </summary>
public class PowerFxTests
{
    private sealed class FixedClock : IClockService
    {
        public DateTime UtcNow { get; set; } = new DateTime(2026, 11, 30, 9, 0, 0, DateTimeKind.Utc);
    }

    private sealed class App
    {
        public FakeHolidaySource Source { get; } = new();
        public PlatformHandler Platform { get; }
        public RecalcEngine Engine { get; }
        public IReadOnlyList<ConnectorFunction> Functions { get; }
        public Dictionary<string, string> Formulas { get; }
        private readonly RuntimeConfig runtime = new();

        public App()
        {
            Platform = new PlatformHandler(Source.SendAsync);
            var config = new PowerFxConfig();
            Functions = config.AddActionConnector(new ConnectorSettings("ContosoHolidays"), Files.OpenApi(out _));
            Engine = new RecalcEngine(config);
            runtime.AddService<IClockService>(new FixedClock());
            runtime.AddService(TimeZoneInfo.Utc);
            runtime.AddRuntimeContext(new PlatformRuntimeContext(Platform));
            Formulas = ReadFormulas();
        }

        /// <summary>Named formulas in App.pa.yaml order, as Power Apps would evaluate them on first use.</summary>
        public void LoadNamedFormulas(params string[] names)
        {
            foreach (var name in names) Engine.UpdateVariable(name, Eval(Formulas[name]));
        }

        public void LoadWorkingDayFunctions()
        {
            var udfs = string.Join("\n", new[] { "IsWorkingDay", "WorkingDaysBetween" }.Select(n => Formulas[n] + ";"));
            var result = Engine.AddUserDefinedFunction(udfs, CultureInfo.InvariantCulture, Engine.EngineSymbols);
            Assert.True(result.IsSuccess, string.Join("; ", result.Errors.Select(e => e.Message)));
        }

        public FormulaValue Eval(string formula) =>
            Engine.EvalAsync(formula, CancellationToken.None, new ParserOptions { AllowsSideEffects = true }, null, runtime).GetAwaiter().GetResult();

        public decimal Number(string formula) => Eval(formula) switch
        {
            DecimalValue d => d.Value,
            NumberValue n => (decimal)n.Value,
            ErrorValue e => throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))),
            var v => throw new InvalidCastException(v.GetType().Name),
        };

        public bool Bool(string formula) => ((BooleanValue)Eval(formula)).Value;
    }

    /// <summary>App.Formulas split at top-level ';' (same idea as episode 3's CanvasSource, simplified: no $"" holes needed here).</summary>
    private static Dictionary<string, string> ReadFormulas()
    {
        var yaml = new YamlStream();
        yaml.Load(new StringReader(File.ReadAllText(Files.App("App.pa.yaml"))));
        var app = (YamlMappingNode)((YamlMappingNode)yaml.Documents[0].RootNode).Children[new YamlScalarNode("App")];
        var text = ((YamlScalarNode)((YamlMappingNode)app.Children[new YamlScalarNode("Properties")]).Children[new YamlScalarNode("Formulas")]).Value!.TrimStart('=');

        var parts = new List<string>();
        int depth = 0, start = 0;
        char? quote = null;
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            if (quote != null) { if (c == quote) quote = null; continue; }
            switch (c)
            {
                case '"' or '\'': quote = c; break;
                case '(' or '[' or '{': depth++; break;
                case ')' or ']' or '}': depth--; break;
                case ';' when depth == 0: parts.Add(text[start..i]); start = i + 1; break;
            }
        }
        return parts.Select(p => p.Trim()).Where(p => p.Length > 0).ToDictionary(
            p => System.Text.RegularExpressions.Regex.Match(p, @"^[A-Za-z_][A-Za-z0-9_]*").Value,
            p => p.Contains("):") ? p : p[(p.IndexOf('=') + 1)..].Trim());
    }

    [Fact]
    public void Makers_see_GetDaysOff_and_ListPublicHolidays_but_not_the_internal_country_list()
    {
        var app = new App();
        Assert.Equal(new[] { "GetDaysOff", "ListPublicHolidays" }, app.Functions.Select(f => f.Name).OrderBy(n => n));

        var daysOff = app.Functions.Single(f => f.Name == "GetDaysOff");
        Assert.Equal(new[] { "CountryCode", "fromYear" }, daysOff.RequiredParameters.Select(p => p.Name));
        Assert.Equal(new[] { "toYear", "subdivision" }, daysOff.OptionalParameters.Select(p => p.Name));
    }

    [Fact]
    public void The_DaysOff_formula_from_the_app_is_one_connector_call_for_three_years()
    {
        var app = new App();
        app.LoadNamedFormulas("OfficeCountry", "OfficeSubdivision", "DaysOff", "Holidays");

        Assert.Equal(new[] { "GetDaysOff /api/v3/DaysOff/PT?fromYear=2025&toYear=2027&subdivision=" }, app.Platform.Calls);
        Assert.Equal(3, app.Source.Requests.Count); // the script asks the source once per year
        Assert.Equal(39m, app.Number("CountRows(Holidays)")); // 13 nationwide public holidays a year in 2025-2027
        Assert.True(app.Bool("Date(2026, 12, 8) in Holidays"));
        Assert.True(app.Bool("Date(2027, 1, 1) in Holidays"));
        Assert.False(app.Bool("Date(2026, 2, 17) in Holidays")); // Carnival: Optional
        Assert.False(app.Bool("Date(2026, 6, 1) in Holidays"));  // Azores Day: regional
    }

    [Fact]
    public void Episode_3s_working_day_functions_now_use_the_connector_holidays()
    {
        var app = new App();
        app.LoadNamedFormulas("OfficeCountry", "OfficeSubdivision", "DaysOff", "Holidays");
        app.LoadWorkingDayFunctions();

        // Due Wed 23 Dec 2026, counted on Mon 4 Jan 2027: 24, 28, 29, 30, 31 Dec and 4 Jan (25 Dec and 1 Jan are holidays).
        Assert.Equal(6m, app.Number("WorkingDaysBetween(Date(2026, 12, 23), Date(2027, 1, 4))"));
        Assert.False(app.Bool("IsWorkingDay(Date(2026, 6, 4))")); // Corpus Christi, never in episode 3's hard-coded list
    }

    [Fact]
    public void A_Madeira_office_gets_its_own_days_off_by_changing_one_named_formula()
    {
        var app = new App();
        app.Engine.UpdateVariable("OfficeCountry", FormulaValue.New("PT"));
        app.Engine.UpdateVariable("OfficeSubdivision", FormulaValue.New("PT-30"));
        app.LoadNamedFormulas("DaysOff", "Holidays");
        app.LoadWorkingDayFunctions();

        Assert.True(app.Bool("Date(2026, 7, 1) in Holidays"));  // Madeira Day
        // Fri 26 Dec 2025 is St. Stephen's Day in Madeira only: Mon 22 to Mon 29 Dec 2025 is 3 working days there, 4 in Lisbon.
        Assert.Equal(3m, app.Number("WorkingDaysBetween(Date(2025, 12, 22), Date(2025, 12, 29))"));
    }

    [Fact]
    public void The_gotcha_using_the_raw_list_makes_Carnival_a_day_off()
    {
        var app = new App();
        // What a maker writes first: every row the source returns is a holiday.
        app.Engine.UpdateVariable("Holidays", app.Eval("ForAll(ContosoHolidays.ListPublicHolidays(2026, \"PT\"), ThisRecord.date)"));
        app.LoadWorkingDayFunctions();
        var naive = app.Number("WorkingDaysBetween(Date(2026, 2, 16), Date(2026, 2, 18))");

        var fixedApp = new App();
        fixedApp.LoadNamedFormulas("OfficeCountry", "OfficeSubdivision", "DaysOff", "Holidays");
        fixedApp.LoadWorkingDayFunctions();
        var filtered = fixedApp.Number("WorkingDaysBetween(Date(2026, 2, 16), Date(2026, 2, 18))");

        Assert.Equal(1m, naive);     // Tue 17 Feb counted as a holiday
        Assert.Equal(2m, filtered);  // Carnival is "Optional" in Portugal: offices are open
    }

    [Fact]
    public void An_unknown_country_is_an_error_value_in_the_app_not_an_empty_calendar()
    {
        var app = new App();
        var result = app.Eval("ContosoHolidays.GetDaysOff(\"XX\", 2026)");

        var error = Assert.IsType<ErrorValue>(result);
        Assert.NotEmpty(error.Errors);
        Assert.Contains(error.Errors, e => e.Message.Contains("404") || e.Message.Contains("not recognized"));
    }
}
