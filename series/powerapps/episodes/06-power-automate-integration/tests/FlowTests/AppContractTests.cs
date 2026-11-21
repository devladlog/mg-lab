using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using FlowTests.Wdl;
using Microsoft.OpenApi.Readers;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Connectors;
using Microsoft.PowerFx.Types;
using Newtonsoft.Json.Linq;
using Xunit;
using YamlDotNet.RepresentationModel;

namespace FlowTests;

/// <summary>
/// The app side of the contract. The button's formulas come from src/app/Src/LoansScreen.pa.yaml and run on the
/// open-source Power Fx interpreter. SendLoanReminder.Run is a stand-in built from the flow's own trigger and
/// response schemas (OpenAPI via Microsoft.PowerFx.Connectors), and each call runs the real flow definition
/// on the FlowRunner with the fake connectors. It checks that app and flow agree; it isn't how Power Apps hosts flows.
/// </summary>
public class AppContractTests
{
    private sealed class Notify(List<string> calls) : ReflectionFunction("Notify", FormulaType.Boolean, FormulaType.String, FormulaType.String)
    {
        public BooleanValue Execute(StringValue message, StringValue type) { calls.Add($"{type.Value}: {message.Value}"); return FormulaValue.New(true); }
    }

    /// <summary>HTTP handler behind SendLoanReminder.Run: body {"text": id} -> FlowRunner -> the flow's response.</summary>
    private sealed class FlowEndpoint(FakeConnectors fakes) : HttpMessageHandler
    {
        public HttpStatusCode? FailWith { get; set; }
        public List<JObject> Requests { get; } = new();

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            var body = JObject.Parse(await request.Content!.ReadAsStringAsync(ct));
            Requests.Add(body);
            if (FailWith is { } status) return new HttpResponseMessage(status) { Content = new StringContent("""{"error":{"code":"WorkflowTriggerIsNotEnabled","message":"The workflow is disabled."}}""", Encoding.UTF8, "application/json") };
            var run = new FlowRunner(Files.Definition(), fakes.Handle, Flow.Now).Run(body);
            return run.Response is null
                ? new HttpResponseMessage(HttpStatusCode.GatewayTimeout)
                : new HttpResponseMessage((HttpStatusCode)run.Response.StatusCode) { Content = new StringContent(run.Response.Body.ToString(), Encoding.UTF8, "application/json") };
        }
    }

    private sealed class Context(HttpMessageHandler handler) : BaseRuntimeConnectorContext
    {
        public override TimeZoneInfo TimeZoneInfo => TimeZoneInfo.Utc;
        public override HttpMessageInvoker GetInvoker(string @namespace) => new(handler, disposeHandler: false);
    }

    private sealed class Screen
    {
        public FakeConnectors Fakes { get; } = new();
        public FlowEndpoint Endpoint { get; }
        public List<string> Notifications { get; } = new();
        public RecalcEngine Engine { get; }
        public IReadOnlyList<ConnectorFunction> FlowFunctions { get; }
        private readonly RuntimeConfig runtime = new();
        private static readonly RecordType LoanRow = RecordType.Empty().Add("contoso_loanid", FormulaType.Guid);

        public Screen()
        {
            Endpoint = new FlowEndpoint(Fakes);
            var config = new PowerFxConfig();
            config.EnableSetFunction();
            config.AddFunction(new Notify(Notifications));
            FlowFunctions = config.AddActionConnector(new ConnectorSettings("SendLoanReminder"), FlowAsOpenApi());
            Engine = new RecalcEngine(config);
            Engine.UpdateVariable("sendingLoan", FormulaValue.NewBlank(FormulaType.Guid));
            Engine.UpdateVariable("NotificationType", Enum("Success", "Warning", "Error", "Information"));
            Engine.UpdateVariable("DisplayMode", Enum("Edit", "Disabled", "View"));
            runtime.AddRuntimeContext(new Context(Endpoint));
        }

        public void ThisItem(Guid loanId) =>
            Engine.UpdateVariable("ThisItem", FormulaValue.NewRecordFromFields(LoanRow, new NamedValue("contoso_loanid", FormulaValue.New(loanId))));

        public FormulaValue Eval(string formula)
        {
            var result = Engine.EvalAsync(formula.TrimStart('='), CancellationToken.None, new ParserOptions { AllowsSideEffects = true }, null, runtime).GetAwaiter().GetResult();
            return result is ErrorValue e ? throw new InvalidOperationException(string.Join("; ", e.Errors.Select(x => x.Message))) : result;
        }

        private static RecordValue Enum(params string[] names) =>
            FormulaValue.NewRecordFromFields(names.Select(n => new NamedValue(n, FormulaValue.New(n))));
    }

    /// <summary>The flow seen as an API: POST with the trigger's input schema, 200 with the Respond action's schema.</summary>
    private static Microsoft.OpenApi.Models.OpenApiDocument FlowAsOpenApi()
    {
        var definition = Files.Definition();
        var input = definition["triggers"]!["manual"]!["inputs"]!["schema"]!;
        var output = definition.Descendants().OfType<JObject>().First(o => (string?)o["type"] == "Response")["inputs"]!["schema"]!;
        var swagger = new JObject
        {
            ["swagger"] = "2.0",
            ["info"] = new JObject { ["title"] = "SendLoanReminder", ["version"] = "1.0" },
            ["host"] = "flow.invalid",
            ["basePath"] = "/",
            ["schemes"] = new JArray("https"),
            ["paths"] = new JObject
            {
                ["/run"] = new JObject
                {
                    ["post"] = new JObject
                    {
                        ["operationId"] = "Run",
                        ["parameters"] = new JArray(new JObject { ["name"] = "body", ["in"] = "body", ["required"] = true, ["schema"] = input.DeepClone() }),
                        ["responses"] = new JObject { ["200"] = new JObject { ["description"] = "Respond to a Power App or flow", ["schema"] = output.DeepClone() } },
                    },
                },
            },
        };
        using var stream = new MemoryStream(Encoding.UTF8.GetBytes(swagger.ToString()));
        var doc = new OpenApiStreamReader().Read(stream, out var diagnostic);
        Assert.Empty(diagnostic.Errors);
        return doc;
    }

    private static Dictionary<string, string> Button()
    {
        var yaml = new YamlStream();
        yaml.Load(new StringReader(File.ReadAllText(Files.LoansScreen)));
        var button = yaml.Documents[0].RootNode.AllNodes.OfType<YamlMappingNode>()
            .First(m => m.Children.ContainsKey(new YamlScalarNode("btnRemind")));
        var props = (YamlMappingNode)((YamlMappingNode)button.Children[new YamlScalarNode("btnRemind")]).Children[new YamlScalarNode("Properties")];
        return props.Children.ToDictionary(k => ((YamlScalarNode)k.Key).Value!, v => ((YamlScalarNode)v.Value).Value!);
    }

    [Fact]
    public void The_button_passes_one_argument_per_trigger_input_and_reads_only_declared_outputs()
    {
        var onSelect = Button()["OnSelect"];
        var definition = Files.Definition();
        var inputs = ((JObject)definition["triggers"]!["manual"]!["inputs"]!["schema"]!["properties"]!).Count;
        var outputs = ((JObject)definition.Descendants().OfType<JObject>().First(o => (string?)o["type"] == "Response")["inputs"]!["schema"]!["properties"]!)
            .Properties().Select(p => p.Name).ToHashSet();

        var call = Regex.Match(onSelect, @"SendLoanReminder\.Run\((?<args>[^()]*(\([^()]*\))?[^()]*)\)");
        Assert.True(call.Success);
        Assert.Equal(inputs, call.Groups["args"].Value.Split(',').Length);
        var read = Regex.Matches(onSelect, @"result\.(\w+)").Select(m => m.Groups[1].Value).ToHashSet();
        Assert.Equal(new HashSet<string> { "sent", "message" }, read);
        Assert.Subset(outputs, read);
    }

    [Fact]
    public void Power_Fx_sees_Run_with_one_required_text_parameter()
    {
        var screen = new Screen();
        var run = Assert.Single(screen.FlowFunctions);
        Assert.Equal("Run", run.Name);
        Assert.Single(run.RequiredParameters);
        Assert.Empty(run.OptionalParameters);
    }

    [Fact]
    public void Send_reminder_on_an_overdue_loan_sends_the_email_and_shows_the_flows_message()
    {
        var screen = new Screen();
        screen.ThisItem(FakeConnectors.OverdueLoan);
        screen.Eval(Button()["OnSelect"]);

        Assert.Equal(FakeConnectors.OverdueLoan.ToString(), (string)Assert.Single(screen.Endpoint.Requests)["text"]!);
        Assert.Single(screen.Fakes.SentMail);
        Assert.Equal(new[] { "Success: Reminder sent to alex.demo@contoso.com for CT-0043." }, screen.Notifications);
        Assert.IsType<BlankValue>(screen.Eval("sendingLoan")); // buttons enabled again
    }

    [Fact]
    public void A_loan_that_was_returned_shows_a_warning_with_the_reason()
    {
        var screen = new Screen();
        screen.ThisItem(FakeConnectors.ReturnedLoan);
        screen.Eval(Button()["OnSelect"]);

        Assert.Empty(screen.Fakes.SentMail);
        Assert.Equal(new[] { "Warning: No reminder sent: it was already returned." }, screen.Notifications);
    }

    [Fact]
    public void When_the_flow_cannot_run_the_user_sees_an_error_and_the_buttons_come_back()
    {
        var screen = new Screen();
        screen.Endpoint.FailWith = HttpStatusCode.BadRequest; // e.g. the flow is turned off (WorkflowTriggerIsNotEnabled)
        screen.ThisItem(FakeConnectors.OverdueLoan);
        screen.Eval(Button()["OnSelect"]);

        var note = Assert.Single(screen.Notifications);
        Assert.StartsWith("Error: The reminder flow didn't run: ", note);
        Assert.IsType<BlankValue>(screen.Eval("sendingLoan"));
    }

    [Fact]
    public void While_one_reminder_is_sending_every_reminder_button_is_disabled()
    {
        var screen = new Screen();
        var props = Button();
        screen.ThisItem(FakeConnectors.OverdueLoan);
        Assert.Equal("Send reminder", ((StringValue)screen.Eval(props["Text"])).Value);
        Assert.Equal("Edit", ((StringValue)screen.Eval(props["DisplayMode"])).Value);

        screen.Eval($"Set(sendingLoan, GUID(\"{FakeConnectors.OverdueLoan}\"))");
        Assert.Equal("Sending...", ((StringValue)screen.Eval(props["Text"])).Value);
        screen.ThisItem(FakeConnectors.UpperCaseLoan);                       // another row in the gallery
        Assert.Equal("Send reminder", ((StringValue)screen.Eval(props["Text"])).Value);
        Assert.Equal("Disabled", ((StringValue)screen.Eval(props["DisplayMode"])).Value);
    }
}
