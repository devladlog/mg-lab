using Newtonsoft.Json.Linq;

namespace FlowTests.Wdl;

/// <summary>What a connector action returns in a test: HTTP-like status and body, or a timeout.</summary>
public sealed record ConnectorResult(int Status, JToken Body, bool TimedOut = false)
{
    public static ConnectorResult Ok(JToken body) => new(200, body);
}

public sealed record ConnectorCall(string Connection, string OperationId, JObject Parameters);

public sealed record FlowResponse(string Action, int StatusCode, JObject Body);

public sealed record FlowRun(FlowResponse? Response, IReadOnlyList<FlowResponse> AllResponses,
    IReadOnlyDictionary<string, string> Status, IReadOnlyList<ConnectorCall> Calls);

/// <summary>
/// Runs a cloud flow definition (the "definition" inside clientdata) the way Learn's workflow definition language
/// describes it, for the action types this flow uses: OpenApiConnection (answered by the test), Compose, If, Response.
/// An action runs when every action in its runAfter has finished with one of the listed statuses; otherwise it's
/// Skipped. Actions with an empty runAfter start together at the beginning of their scope.
/// </summary>
public sealed class FlowRunner(JObject definition, Func<ConnectorCall, ConnectorResult> connectors, DateTimeOffset utcNow)
{
    public FlowRun Run(JObject triggerBody)
    {
        var trigger = (JObject)((JObject)definition["triggers"]!).Properties().Single().Value;
        var schema = (JObject)trigger["inputs"]!["schema"]!;
        foreach (var required in schema["required"]?.Select(r => (string)r!) ?? [])
            if (Expressions.IsNull(triggerBody[required]))
                throw new ArgumentException($"trigger input '{required}' ({(string?)schema["properties"]![required]!["title"]}) is required");

        var state = new State(triggerBody, utcNow);
        var calls = new List<ConnectorCall>();
        var responses = new List<FlowResponse>();
        RunScope((JObject)definition["actions"]!, state, calls, responses);
        return new FlowRun(responses.FirstOrDefault(), responses, state.Status, calls);
    }

    private void RunScope(JObject actions, State state, List<ConnectorCall> calls, List<FlowResponse> responses)
    {
        var pending = actions.Properties().Select(p => p.Name).ToList();
        while (pending.Count > 0)
        {
            var ready = pending.Where(name =>
                ((JObject)actions[name]!["runAfter"]!).Properties().All(p => state.Status.ContainsKey(p.Name))).ToList();
            if (ready.Count == 0) throw new InvalidOperationException("runAfter cycle or unknown action among: " + string.Join(", ", pending));

            foreach (var name in ready)
            {
                var action = (JObject)actions[name]!;
                var runAfter = ((JObject)action["runAfter"]!).Properties().ToList();
                var allowed = runAfter.All(p => p.Value.Select(s => (string)s!).Contains(state.Status[p.Name]));
                if (!allowed) { Skip(name, action, state); continue; }
                Execute(name, action, state, calls, responses);
            }
            pending = pending.Except(ready).ToList();
        }
    }

    // A skipped If skips everything inside it, so later runAfter checks see "Skipped", not "missing".
    private static void Skip(string name, JObject action, State state)
    {
        state.Status[name] = "Skipped";
        foreach (var inner in new[] { action["actions"], action["else"]?["actions"] }.OfType<JObject>().SelectMany(a => a.Properties()))
            Skip(inner.Name, (JObject)inner.Value, state);
    }

    private void Execute(string name, JObject action, State state, List<ConnectorCall> calls, List<FlowResponse> responses)
    {
        switch ((string)action["type"]!)
        {
            case "Compose":
                state.Results[name] = Expressions.EvaluateValue(action["inputs"]!, state);
                state.Status[name] = "Succeeded";
                break;

            case "OpenApiConnection":
            {
                var host = action["inputs"]!["host"]!;
                var parameters = (JObject)Expressions.EvaluateValue(action["inputs"]!["parameters"]!, state);
                var call = new ConnectorCall((string)host["connectionName"]!, (string)host["operationId"]!, parameters);
                calls.Add(call);
                var result = connectors(call);
                state.Results[name] = new JObject { ["statusCode"] = result.Status, ["body"] = result.Body };
                state.Bodies[name] = result.Body;
                state.Status[name] = result.TimedOut ? "TimedOut" : result.Status is >= 200 and < 300 ? "Succeeded" : "Failed";
                break;
            }

            case "If":
            {
                var branch = EvaluateCondition(action["expression"]!, state) ? (JObject)action["actions"]! : (JObject?)action["else"]?["actions"];
                var other = branch == action["actions"] ? (JObject?)action["else"]?["actions"] : (JObject)action["actions"]!;
                foreach (var p in other?.Properties() ?? []) Skip(p.Name, (JObject)p.Value, state);
                if (branch != null) RunScope(branch, state, calls, responses);
                state.Status[name] = "Succeeded";
                break;
            }

            case "Response":
            {
                var inputs = (JObject)Expressions.EvaluateValue(action["inputs"]!, state);
                responses.Add(new FlowResponse(name, (int)inputs["statusCode"]!, (JObject)inputs["body"]!));
                state.Status[name] = "Succeeded";
                break;
            }

            default:
                throw new NotSupportedException($"action type {(string)action["type"]!} ({name})");
        }
    }

    /// <summary>Condition objects as the designer writes them: and / or / not / equals / less / ..., operands are values.</summary>
    public static bool EvaluateCondition(JToken expression, IContext context)
    {
        var (op, args) = ((JObject)expression).Properties().Single() is var p ? (p.Name, p.Value) : default;
        JToken Val(int i) => Expressions.EvaluateValue(args[i]!, context);
        return op switch
        {
            "and" => args.All(a => EvaluateCondition(a, context)),
            "or" => args.Any(a => EvaluateCondition(a, context)),
            "not" => !EvaluateCondition(args, context),
            "equals" => JToken.DeepEquals(Val(0), Val(1)),
            _ => throw new NotSupportedException("condition operator " + op),
        };
    }

    private sealed class State(JObject triggerBody, DateTimeOffset utcNow) : IContext
    {
        public Dictionary<string, string> Status { get; } = new();
        public Dictionary<string, JToken> Results { get; } = new();
        public Dictionary<string, JToken> Bodies { get; } = new();
        public JToken TriggerBody => triggerBody;
        public DateTimeOffset UtcNow => utcNow;
        public JToken Body(string action) => Bodies.TryGetValue(action, out var b) ? b
            
            : Results.TryGetValue(action, out var o) ? o : throw new FlowExpressionException($"body('{action}'): action didn't run");
        public JToken Outputs(string action) => Results.TryGetValue(action, out var o) ? o
            : throw new FlowExpressionException($"outputs('{action}'): action didn't run");
    }
}
