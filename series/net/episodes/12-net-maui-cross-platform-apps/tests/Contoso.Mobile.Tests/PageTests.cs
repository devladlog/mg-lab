using System.Xml.Linq;
using Contoso.Mobile.Core.Models;
using Contoso.Mobile.Core.Offline;
using Contoso.Mobile.Core.ViewModels;
using Contoso.Mobile.Views;
using Microsoft.Extensions.Time.Testing;

namespace Contoso.Mobile.Tests;

/// <summary>
/// The REAL pages from the MAUI app project (compiled here from the same .xaml files), driven without a device:
/// real controls, real bindings, real view models. What this can't show: how it looks, or platform behaviour.
/// </summary>
public class PageTests : IDisposable
{
    private static readonly XNamespace X = "http://schemas.microsoft.com/winfx/2009/xaml";
    private readonly TempDir _dir = new();
    private readonly FakeApi _api = new();
    private readonly FakeConnectivity _net = new();
    private readonly FileOutbox _outbox;
    private readonly FileRequestCache _cache;
    private readonly SyncService _sync;

    public PageTests()
    {
        EnsureApplication();
        _outbox = new FileOutbox(_dir.File("outbox.json")); _cache = new FileRequestCache(_dir.File("cache.json"));
        _sync = new SyncService(_outbox, _api, _net);
    }

    public void Dispose() => _dir.Dispose();

    /// <summary>The pages use {StaticResource Primary} and friends: give them the real values from Resources/Styles/Colors.xaml.</summary>
    private static void EnsureApplication()
    {
        Microsoft.Maui.Dispatching.DispatcherProvider.SetCurrent(new TestDispatcherProvider());
        if (Application.Current is not null) return;
        var resources = new ResourceDictionary();
        foreach (var color in XDocument.Load(Repo.Path("src/Contoso.Mobile/Resources/Styles/Colors.xaml")).Root!.Elements().Where(e => e.Name.LocalName == "Color"))
            resources[(string)color.Attribute(X + "Key")!] = Color.FromArgb(color.Value.Trim());
        _ = new Application { Resources = resources };
    }

    private NewRequestPage NewPage(out NewRequestViewModel vm)
    {
        vm = new NewRequestViewModel(_outbox, _sync, new FakeTimeProvider(DateTimeOffset.Parse("2026-11-21T10:00:00Z")))
        { Culture = System.Globalization.CultureInfo.InvariantCulture };
        return new NewRequestPage(vm);
    }

    private static T Find<T>(Element root, string automationId) where T : Element =>
        Descendants(root).OfType<T>().Single(e => e.AutomationId == automationId);

    private static IEnumerable<Element> Descendants(Element root)
    {
        yield return root;
        foreach (var child in ((IVisualTreeElement)root).GetVisualChildren().OfType<Element>())
            foreach (var d in Descendants(child)) yield return d;
    }

    private static async Task Until(Func<bool> condition)
    {
        for (var i = 0; i < 200 && !condition(); i++) await Task.Delay(10);
        Assert.True(condition(), "condition not reached in 2 s");
    }

    [Fact]
    public void The_new_request_form_is_wired_to_its_view_model_both_ways()
    {
        var page = NewPage(out var vm);
        Assert.Same(vm, page.BindingContext);

        Find<Entry>(page, "TitleEntry").Text = "Standing desks";
        Find<Entry>(page, "AmountEntry").Text = "12000";
        Find<Entry>(page, "RequestedByEntry").Text = "alex.demo@contoso.com";
        var picker = Find<Picker>(page, "DepartmentPicker");
        Assert.Equal(["FIN", "IT", "OPS"], picker.ItemsSource.Cast<string>());
        picker.SelectedItem = "OPS";
        Assert.Equal(("Standing desks", "12000", "alex.demo@contoso.com", "OPS"), (vm.Title, vm.AmountText, vm.RequestedBy, vm.DepartmentCode));

        vm.Title = "Changed in code";   // and the other way
        Assert.Equal("Changed in code", Find<Entry>(page, "TitleEntry").Text);
        Assert.Equal(Keyboard.Numeric, Find<Entry>(page, "AmountEntry").Keyboard);
        Assert.Equal(Keyboard.Email, Find<Entry>(page, "RequestedByEntry").Keyboard);
    }

    [Fact]
    public async Task Tapping_Submit_with_mistakes_shows_them_on_the_page()
    {
        var page = NewPage(out _);
        ((IButtonController)Find<Button>(page, "SubmitButton")).SendClicked();
        await Until(() => !string.IsNullOrEmpty(Find<Label>(page, "ErrorsLabel").Text));
        Assert.Contains("Title:", Find<Label>(page, "ErrorsLabel").Text);
        Assert.Empty(_api.Submitted);
    }

    [Fact]
    public async Task A_double_click_on_Submit_sends_one_request_because_the_button_disables_itself()
    {
        _api.Delay = TimeSpan.FromMilliseconds(200);
        var page = NewPage(out _);
        Find<Entry>(page, "TitleEntry").Text = "Standing desks";
        Find<Entry>(page, "AmountEntry").Text = "12000";
        Find<Entry>(page, "RequestedByEntry").Text = "alex.demo@contoso.com";
        Find<Picker>(page, "DepartmentPicker").SelectedItem = "FIN";

        var button = Find<Button>(page, "SubmitButton");
        ((IButtonController)button).SendClicked();
        Assert.False(button.IsEnabled);                   // the command is running: the button is off
        ((IButtonController)button).SendClicked();        // second click of the double click: ignored
        await Until(() => button.IsEnabled);
        Assert.Single(_api.Submitted);
    }

    [Fact]
    public async Task Tapping_Submit_offline_stores_the_draft_and_the_page_says_so()
    {
        _net.IsOnline = false;
        var page = NewPage(out _);
        Find<Entry>(page, "TitleEntry").Text = "Standing desks";
        Find<Entry>(page, "AmountEntry").Text = "12000";
        Find<Entry>(page, "RequestedByEntry").Text = "alex.demo@contoso.com";
        Find<Picker>(page, "DepartmentPicker").SelectedItem = "FIN";

        ((IButtonController)Find<Button>(page, "SubmitButton")).SendClicked();
        await Until(() => Find<Label>(page, "ResultLabel").Text?.Length > 0);
        Assert.Contains("back online", Find<Label>(page, "ResultLabel").Text);
        Assert.Single(await _outbox.ListAsync());
    }

    [Fact]
    public async Task The_list_page_loads_when_it_appears_and_each_row_template_shows_its_row()
    {
        _api.Server.Add(new RequestItem(1, "Standing desks", "FIN", 12_000m, "alex.demo@contoso.com", "Reserved", DateTime.UtcNow));
        var vm = new RequestListViewModel(_api, _cache, _outbox, _sync, _net, new InlineUi());
        var page = new RequestListPage(vm);

        // Shell calls the protected OnAppearing when the page is shown (Page.SendAppearing does nothing without a window): call it the same way.
        typeof(RequestListPage).GetMethod("OnAppearing", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.DeclaredOnly)!.Invoke(page, null);
        await Until(() => vm.Rows.Count == 1);

        Assert.Equal("Up to date.", Find<Label>(page, "StatusLabel").Text);
        var rows = Find<CollectionView>(page, "RequestRows");
        Assert.Same(vm.Rows, rows.ItemsSource);
        Assert.Equal(["New"], page.ToolbarItems.Select(t => t.Text));

        var cell = (VerticalStackLayout)rows.ItemTemplate.CreateContent();
        cell.BindingContext = vm.Rows[0];
        var labels = cell.Children.OfType<Label>().ToList();
        Assert.Equal(["Standing desks", "FIN · 12,000 · alex.demo@contoso.com", "Budget reserved"], labels.Select(l => l.Text));
        cell.BindingContext = new RequestRow("Refused", "IT · 900", "Needs attention: x", true, true);   // the data trigger flips the colour
        Assert.Equal(Application.Current!.Resources["Warning"], labels[2].TextColor);
    }

    [Fact]
    public void Every_resource_key_the_pages_use_exists_in_the_real_style_files()
    {
        var defined = Directory.GetFiles(Repo.Path("src/Contoso.Mobile/Resources/Styles"), "*.xaml")
            .SelectMany(f => XDocument.Load(f).Root!.Descendants().Select(e => (string?)e.Attribute(X + "Key"))).Where(k => k is not null).ToHashSet();

        var used = Directory.GetFiles(Repo.Path("src/Contoso.Mobile/Views"), "*.xaml")
            .SelectMany(f => System.Text.RegularExpressions.Regex.Matches(File.ReadAllText(f), @"\{(?:Static|Dynamic)Resource\s+(\w+)\}").Select(m => m.Groups[1].Value))
            .Distinct().ToList();

        Assert.NotEmpty(used);
        Assert.Empty(used.Where(k => !defined.Contains(k)));
    }
}

public class AppConfigurationTests
{
    private static XDocument Load(string path) => XDocument.Load(Repo.Path(path));

    [Fact]
    public void Android_asks_for_the_permissions_Connectivity_and_HttpClient_need_and_points_at_the_network_config()
    {
        var manifest = Load("src/Contoso.Mobile/Platforms/Android/AndroidManifest.xml").Root!;
        XNamespace android = "http://schemas.android.com/apk/res/android";
        var permissions = manifest.Elements("uses-permission").Select(e => (string)e.Attribute(android + "name")!).ToList();
        Assert.Contains("android.permission.ACCESS_NETWORK_STATE", permissions);   // Learn: Connectivity throws PermissionException without it
        Assert.Contains("android.permission.INTERNET", permissions);
        Assert.Equal("@xml/network_security_config", (string)manifest.Element("application")!.Attribute(android + "networkSecurityConfig")!);
    }

    [Fact]
    public void Cleartext_HTTP_is_allowed_for_the_emulator_alias_and_nothing_else()
    {
        var config = Load("src/Contoso.Mobile/Platforms/Android/Resources/xml/network_security_config.xml").Root!;
        var domainConfig = Assert.Single(config.Elements("domain-config"));
        Assert.Equal("true", (string)domainConfig.Attribute("cleartextTrafficPermitted")!);
        Assert.Equal(["10.0.2.2"], domainConfig.Elements("domain").Select(d => d.Value));
        Assert.Null(config.Element("base-config"));   // the default stays: no cleartext anywhere else
    }

    [Fact]
    public void The_app_uses_cleartext_traffic_in_Debug_builds_only()
    {
        var code = File.ReadAllText(Repo.Path("src/Contoso.Mobile/Platforms/Android/MainApplication.cs"));
        Assert.Matches(@"#if DEBUG\s*\[Application\(UsesCleartextTraffic = true\)\]\s*#else\s*\[Application\]\s*#endif", code);
    }

    [Fact]
    public void The_project_targets_android_everywhere_windows_on_windows_and_no_apple_platform()
    {
        var csproj = File.ReadAllText(Repo.Path("src/Contoso.Mobile/Contoso.Mobile.csproj"));
        Assert.Contains("<TargetFrameworks>net10.0-android</TargetFrameworks>", csproj);
        Assert.Contains("net10.0-windows10.0.19041.0", csproj);
        Assert.DoesNotContain("-ios", csproj); Assert.DoesNotContain("maccatalyst", csproj);
        Assert.Contains("<UseMaui>true</UseMaui>", csproj);
        Assert.Contains("<MauiXamlInflator>SourceGen</MauiXamlInflator>", csproj);
    }
}
