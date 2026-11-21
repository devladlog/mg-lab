using System.Globalization;
using System.Text.RegularExpressions;
using Microsoft.PowerFx;
using Xunit;

namespace EquipmentDesk.Components.Tests;

/// <summary>
/// Lints that turn Microsoft Learn's component and component library rules into failing tests. Each rule names its
/// source. These read the source; they don't need Power Apps.
/// </summary>
public class LibraryRulesTests
{
    private static readonly CanvasSource App = SourceTests.AppSource;
    private static readonly CanvasSource Library = SourceTests.LibrarySource;

    private static IEnumerable<(string Where, string Formula)> LibraryFormulas() =>
        Library.Components.Values.SelectMany(d => d.Properties.Select(p => ($"{d.Name}.{p.Key}", p.Value)))
            .Concat(Library.Controls.Values.Where(c => c.InComponent).SelectMany(c => c.Properties.Select(p => ($"{c.Owner}/{c.Name}.{p.Key}", p.Value))));

    [Fact]
    public void Every_library_component_says_whether_apps_may_customize_it()
    {
        // pa.yaml schema: AllowCustomization "should always be specified for component definitions in a component library".
        // Learn: with customization on, "Edit component" makes a local copy and the link to the library is removed.
        foreach (var d in Library.Components.Values) Assert.True(d.AllowCustomization.HasValue, d.Name);
        Assert.All(Library.Components.Values, d => Assert.False(d.AllowCustomization));
    }

    [Fact]
    public void No_library_component_asks_for_app_scope()
    {
        // Learn: "Components in a component library can never access app scope."
        Assert.All(Library.Components.Values, d => Assert.Null(d.AccessAppScope));
    }

    [Fact]
    public void A_library_stays_under_twenty_components()
    {
        // Learn (component library ALM): "Limit the number of components in a library to 20 to get optimal performance."
        Assert.InRange(Library.Components.Count, 1, 20);
    }

    [Fact]
    public void Library_formulas_use_no_data_sources_no_flows_and_no_UpdateContext()
    {
        // Learn: data sources can't be saved with components; flows in component libraries aren't supported;
        // components don't support UpdateContext.
        var forbidden = new Regex(@"\b(Loans|Equipment)\b|\.Run\(|\bUpdateContext\(|\bPatch\(|\bCollect\(");
        var hits = LibraryFormulas().Where(f => forbidden.IsMatch(f.Formula)).Select(f => f.Where).ToList();
        Assert.Empty(hits);
    }

    [Fact]
    public void No_code_components_in_the_library()
    {
        // Learn: "Code components aren't supported inside component libraries."
        Assert.DoesNotContain(Library.Controls.Values, c => c.Type == "CodeComponent");
    }

    private static IEnumerable<string> ComponentsInsideGalleries(CanvasSource s) =>
        s.Controls.Values.Where(c => c.Type == "CanvasComponent" && Ancestors(s, c).Any(a => a.Type.StartsWith("Gallery") || a.Type.StartsWith("Form")))
            .Select(c => c.Name);

    private static IEnumerable<CanvasSource.ControlInfo> Ancestors(CanvasSource s, CanvasSource.ControlInfo c)
    {
        for (var p = c.Parent; p != null; p = s.Controls[p].Parent) yield return s.Controls[p];
    }

    [Fact]
    public void No_component_instance_sits_inside_a_gallery_or_a_form()
    {
        // Learn (known limitations): "You can't insert a component into a gallery or a form".
        Assert.Empty(ComponentsInsideGalleries(App));
        Assert.Empty(ComponentsInsideGalleries(Library));
    }

    [Fact]
    public void The_gallery_lint_catches_a_status_badge_in_a_row()
    {
        // The design we wanted first: a StatusBadge component per gallery row. The lint must refuse it.
        var dir = Directory.CreateTempSubdirectory("pa-yaml-");
        try
        {
            File.WriteAllText(Path.Combine(dir.FullName, "Bad.pa.yaml"), """
                Screens:
                  BadScreen:
                    Children:
                      - galLoans:
                          Control: Gallery
                          Children:
                            - badge:
                                Control: CanvasComponent
                                ComponentName: StatusBadge
                """);
            Assert.Equal(new[] { "badge" }, ComponentsInsideGalleries(new CanvasSource(dir.FullName)));
        }
        finally { dir.Delete(true); }
    }

    [Fact]
    public void Inside_a_component_every_Definition_dot_Property_is_a_declared_custom_property()
    {
        foreach (var (where, formula) in LibraryFormulas())
        {
            var owner = where.Split('.', '/')[0];
            var def = Library.Components[owner];
            foreach (Match m in Regex.Matches(formula, $@"\b{owner}\.([A-Za-z_][A-Za-z0-9_]*)"))
                Assert.True(def.CustomProperties.ContainsKey(m.Groups[1].Value), $"{where}: {owner}.{m.Groups[1].Value} isn't declared");
        }
    }

    [Fact]
    public void Inputs_have_defaults_and_events_return_nothing()
    {
        var props = Library.Components.Values.SelectMany(d => d.CustomProperties.Values).ToList();
        Assert.All(props.Where(p => p.Kind == "Input"), p => Assert.NotNull(p.Default));
        Assert.All(props.Where(p => p.Kind == "Event"), p => Assert.Equal("None", p.ReturnType));
        // An output function needs its formula in the definition's Properties.
        foreach (var d in Library.Components.Values)
            foreach (var p in d.CustomProperties.Values.Where(p => p.Kind is "Output" or "OutputFunction" or "Action"))
                Assert.True(d.Properties.ContainsKey(p.Name), $"{d.Name}.{p.Name} has no formula");
    }

    public static IEnumerable<object[]> OutputFunctions() =>
        Library.Components.Values.SelectMany(d => d.CustomProperties.Values.Where(p => p.Kind == "OutputFunction").Select(p => new object[] { d.Name, p.Name }));

    [Theory]
    [MemberData(nameof(OutputFunctions))]
    public void A_function_property_binds_with_nothing_but_its_parameters(string component, string property)
    {
        // Learn: "Function properties currently cannot access variables or component values and properties".
        // So compile each one in an EMPTY engine: no app, no component record, no controls, only its parameters.
        var config = new PowerFxConfig();
        config.EnableRegExFunctions(TimeSpan.FromSeconds(1), 10);
        var empty = new RecalcEngine(config);
        var def = Library.Components[component];
        var udf = Harness.Udf("f", def.CustomProperties[property], def.Properties[property]);
        var result = empty.AddUserDefinedFunction(udf, CultureInfo.InvariantCulture, empty.EngineSymbols);
        Assert.True(result.IsSuccess, $"{component}.{property}: " + string.Join("; ", result.Errors.Select(e => e.Message)));
    }

    [Fact]
    public void The_purity_check_does_fail_when_a_function_reads_component_state()
    {
        var config = new PowerFxConfig();
        var empty = new RecalcEngine(config);
        var p = Library.Components["DeskRules"].CustomProperties["StateColor"];
        var result = empty.AddUserDefinedFunction(Harness.Udf("f", p, "=If(DeskHeader.ShowBack, Color.Red, Color.Blue)"), CultureInfo.InvariantCulture, empty.EngineSymbols);
        Assert.False(result.IsSuccess);
    }

    [Fact]
    public void Every_instance_sets_only_what_its_definition_declares()
    {
        string[] standard = ["X", "Y", "Width", "Height", "Visible"];
        foreach (var inst in App.Instances.Concat(Library.Instances))
        {
            var def = Library.Components[inst.ComponentName!];
            foreach (var prop in inst.Properties.Keys.Where(p => !standard.Contains(p)))
            {
                Assert.True(def.CustomProperties.TryGetValue(prop, out var cp), $"{inst.Name}.{prop} isn't a property of {def.Name}");
                // Output values and output functions are defined once, in the component; the app only reads them.
                Assert.True(cp!.Kind is "Input" or "Event" or "InputFunction", $"{inst.Name} sets {cp.Kind} property {prop}");
            }
        }
    }

    [Fact]
    public void App_instances_name_the_same_library_with_a_valid_unique_name()
    {
        var names = App.Instances.Select(i => i.LibraryName).Distinct().ToList();
        Assert.Equal(new[] { "contoso_equipmentdeskkit" }, names);
        // pa.yaml schema: "{PublisherPrefix}_{ComponentLibraryName}", prefix 2-8 lower-case letters/digits.
        Assert.Matches(@"^([a-z][a-z0-9]{1,7})_(\S.{0,63})$", names[0]!);
        // Instances on the library's own test screen don't name a library: the definitions are local there.
        Assert.All(Library.Instances, i => Assert.Null(i.LibraryName));
    }
}
