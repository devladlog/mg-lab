using System.Globalization;
using System.Text;
using Newtonsoft.Json.Linq;

namespace FlowTests.Wdl;

/// <summary>
/// A small interpreter for the Workflow Definition Language expressions this flow uses (Learn: "Reference guide to
/// workflow expression functions"). Not a Logic Apps engine: it implements the listed functions with the documented
/// behaviour and throws on anything else, so a typo or an unsupported function in the flow fails a test.
/// </summary>
public static class Expressions
{
    public static readonly IReadOnlySet<string> Functions = new HashSet<string>
    {
        "triggerBody", "body", "outputs", "parameters", "if", "equals", "not", "and", "or", "empty", "less", "lessOrEquals",
        "greater", "greaterOrEquals", "endsWith", "startsWith", "contains", "toLower", "toUpper", "concat", "coalesce",
        "formatDateTime", "convertFromUtc", "utcNow", "string",
    };

    /// <summary>A JSON value from the definition: "@expr" is evaluated to a typed value, "...@{expr}..." to a string.</summary>
    public static JToken EvaluateValue(JToken value, IContext context) => value switch
    {
        JObject o => new JObject(o.Properties().Select(p => new JProperty(p.Name, EvaluateValue(p.Value, context)))),
        JArray a => new JArray(a.Select(v => EvaluateValue(v, context))),
        JValue { Type: JTokenType.String } s => EvaluateString((string)s!, context),
        _ => value.DeepClone(),
    };

    public static JToken EvaluateString(string text, IContext context)
    {
        if (text.StartsWith("@@")) return new JValue(text[1..]);
        if (text.StartsWith('@') && !text.StartsWith("@{")) return Evaluate(text[1..], context);
        if (!text.Contains("@{")) return new JValue(text);

        var result = new StringBuilder();
        var i = 0;
        while (i < text.Length)
        {
            var start = text.IndexOf("@{", i, StringComparison.Ordinal);
            if (start < 0) { result.Append(text, i, text.Length - i); break; }
            result.Append(text, i, start - i);
            var end = FindClosingBrace(text, start + 2);
            result.Append(AsString(Evaluate(text[(start + 2)..end], context)));
            i = end + 1;
        }
        return new JValue(result.ToString());
    }

    /// <summary>Every expression in a JSON value (for static checks): "@expr" and each "@{expr}".</summary>
    public static IEnumerable<string> ExpressionsIn(JToken value)
    {
        foreach (var s in (value is JContainer c ? c.DescendantsAndSelf() : new[] { value }).OfType<JValue>().Where(v => v.Type == JTokenType.String).Select(v => (string)v!))
        {
            if (s.StartsWith("@@")) continue;
            if (s.StartsWith('@') && !s.StartsWith("@{")) { yield return s[1..]; continue; }
            var i = 0;
            while ((i = s.IndexOf("@{", i, StringComparison.Ordinal)) >= 0)
            {
                var end = FindClosingBrace(s, i + 2);
                yield return s[(i + 2)..end];
                i = end + 1;
            }
        }
    }

    private static int FindClosingBrace(string text, int from)
    {
        var inString = false;
        for (var i = from; i < text.Length; i++)
        {
            if (text[i] == '\'') inString = !inString;           // '' inside a string toggles twice: still fine
            else if (text[i] == '}' && !inString) return i;
        }
        throw new FormatException("unclosed @{ in " + text);
    }

    public static JToken Evaluate(string expression, IContext context) => new Parser(expression).ParseAll().Eval(context);

    public static Node Parse(string expression) => new Parser(expression).ParseAll();

    public static string AsString(JToken? value) => value switch
    {
        null => "",
        JValue { Type: JTokenType.Null } => "",
        JValue { Type: JTokenType.String } s => (string)s!,
        JValue { Type: JTokenType.Boolean } b => (bool)b ? "True" : "False",
        JValue v => Convert.ToString(v.Value, CultureInfo.InvariantCulture) ?? "",
        _ => value.ToString(Newtonsoft.Json.Formatting.None),
    };

    public static bool IsNull(JToken? t) => t is null || t.Type == JTokenType.Null;

    // ---------- AST ----------
    public abstract record Node
    {
        public abstract JToken Eval(IContext c);
        public virtual IEnumerable<Node> Children => [];
        public IEnumerable<Node> Descendants() => Children.SelectMany(ch => ch.Descendants().Prepend(ch));
    }

    public sealed record Literal(JToken Value) : Node
    {
        public override JToken Eval(IContext c) => Value.DeepClone();
    }

    public sealed record Index(Node Target, Node Key, bool Safe) : Node
    {
        public override IEnumerable<Node> Children => [Target, Key];

        public override JToken Eval(IContext c)
        {
            var target = Target.Eval(c);
            var key = Key.Eval(c);
            if (IsNull(target))
                return Safe ? JValue.CreateNull() : throw new FlowExpressionException($"can't select '{AsString(key)}' from null (use ?[ ])");
            if (target is JObject o)
            {
                var prop = o.Property(AsString(key), StringComparison.Ordinal); // strict on purpose: catches contoso_equipmentid vs contoso_EquipmentId
                if (prop != null) return prop.Value;
                return Safe ? JValue.CreateNull() : throw new FlowExpressionException($"property '{AsString(key)}' doesn't exist");
            }
            if (target is JArray a && key.Type == JTokenType.Integer) return a[(int)key];
            throw new FlowExpressionException($"can't index a {target.Type}");
        }
    }

    public sealed record Call(string Name, IReadOnlyList<Node> Args) : Node
    {
        public override IEnumerable<Node> Children => Args;

        public override JToken Eval(IContext c)
        {
            if (!Functions.Contains(Name)) throw new FlowExpressionException($"function '{Name}' isn't supported by this interpreter");
            switch (Name)
            {
                case "if": return Truthy(Args[0].Eval(c)) ? Args[1].Eval(c) : Args[2].Eval(c); // only the chosen branch runs
                case "and": return Args.All(a => Truthy(a.Eval(c)));
                case "or": return Args.Any(a => Truthy(a.Eval(c)));
            }
            var v = Args.Select(a => a.Eval(c)).ToArray();
            return Name switch
            {
                "triggerBody" => c.TriggerBody,
                "body" => c.Body(Str(v[0])),
                "outputs" => c.Outputs(Str(v[0])),
                "parameters" => JValue.CreateNull(),
                "equals" => JToken.DeepEquals(Normalize(v[0]), Normalize(v[1])),
                "not" => !Truthy(v[0]),
                "empty" => IsNull(v[0]) || v[0] switch { JValue { Type: JTokenType.String } s => ((string)s!).Length == 0, JArray a => a.Count == 0, JObject o => !o.HasValues, _ => false },
                "less" => Compare(v[0], v[1]) < 0,
                "lessOrEquals" => Compare(v[0], v[1]) <= 0,
                "greater" => Compare(v[0], v[1]) > 0,
                "greaterOrEquals" => Compare(v[0], v[1]) >= 0,
                // Learn: startsWith / endsWith "isn't case-sensitive"
                "endsWith" => Str(v[0]).EndsWith(Str(v[1]), StringComparison.OrdinalIgnoreCase),
                "startsWith" => Str(v[0]).StartsWith(Str(v[1]), StringComparison.OrdinalIgnoreCase),
                "contains" => v[0] is JArray arr ? arr.Any(x => JToken.DeepEquals(x, v[1])) : Str(v[0]).Contains(Str(v[1]), StringComparison.Ordinal),
                "toLower" => Str(v[0]).ToLowerInvariant(),
                "toUpper" => Str(v[0]).ToUpperInvariant(),
                "concat" => string.Concat(v.Select(AsString)),
                "coalesce" => v.FirstOrDefault(x => !IsNull(x)) ?? JValue.CreateNull(),
                "string" => AsString(v[0]),
                "utcNow" => FormatTimestamp(c.UtcNow, v.Length > 0 ? Str(v[0]) : "o", null),
                "formatDateTime" => FormatTimestamp(ParseTimestamp(Str(v[0])), v.Length > 1 ? Str(v[1]) : "o", v.Length > 2 ? Str(v[2]) : null),
                "convertFromUtc" => ConvertFromUtc(Str(v[0]), Str(v[1]), v.Length > 2 ? Str(v[2]) : "o"),
                _ => throw new FlowExpressionException(Name),
            };
        }

        private static string Str(JToken t) => AsString(t);
        private static JToken Normalize(JToken t) => t is JValue { Type: JTokenType.Integer or JTokenType.Float } n ? new JValue(Convert.ToDecimal(n.Value, CultureInfo.InvariantCulture)) : t;

        private static bool Truthy(JToken t) => t.Type == JTokenType.Boolean ? (bool)t
            : throw new FlowExpressionException($"expected a boolean, got {t.Type} '{AsString(t)}'");

        private static int Compare(JToken a, JToken b)
        {
            if (a.Type is JTokenType.Integer or JTokenType.Float && b.Type is JTokenType.Integer or JTokenType.Float)
                return ((decimal)a).CompareTo((decimal)b);
            if (a.Type == JTokenType.String && b.Type == JTokenType.String) return string.CompareOrdinal((string)a!, (string)b!);
            throw new FlowExpressionException($"can't compare {a.Type} with {b.Type}");
        }

        private static DateTimeOffset ParseTimestamp(string s) =>
            DateTimeOffset.Parse(s, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal);

        private static string FormatTimestamp(DateTimeOffset t, string format, string? locale) =>
            t.UtcDateTime.ToString(format, locale is null ? CultureInfo.InvariantCulture : new CultureInfo(locale));

        // Learn: the destination time zone is a Windows time zone name ("GMT Standard Time" is Lisbon/London).
        private static string ConvertFromUtc(string timestamp, string zone, string format)
        {
            var local = TimeZoneInfo.ConvertTimeFromUtc(ParseTimestamp(timestamp).UtcDateTime, TimeZoneInfo.FindSystemTimeZoneById(zone));
            return local.ToString(format, CultureInfo.InvariantCulture);
        }
    }

    // ---------- parser ----------
    private sealed class Parser(string text)
    {
        private int pos;

        public Node ParseAll()
        {
            var node = ParseExpression();
            SkipSpace();
            if (pos != text.Length) throw new FormatException($"unexpected '{text[pos..]}' in {text}");
            return node;
        }

        private Node ParseExpression()
        {
            var node = ParsePrimary();
            while (true)
            {
                SkipSpace();
                var safe = Peek('?');
                if (safe) pos++;
                if (Peek('['))
                {
                    pos++;
                    var key = ParseExpression();
                    Expect(']');
                    node = new Index(node, key, safe);
                }
                else if (Peek('.'))
                {
                    pos++;
                    node = new Index(node, new Literal(ParseIdentifier()), safe);
                }
                else
                {
                    if (safe) throw new FormatException("'?' must be followed by [ or . in " + text);
                    return node;
                }
            }
        }

        private Node ParsePrimary()
        {
            SkipSpace();
            if (Peek('\''))
            {
                pos++;
                var sb = new StringBuilder();
                while (true)
                {
                    if (pos >= text.Length) throw new FormatException("unclosed string in " + text);
                    if (text[pos] == '\'')
                    {
                        if (pos + 1 < text.Length && text[pos + 1] == '\'') { sb.Append('\''); pos += 2; continue; } // '' is a quote
                        pos++;
                        break;
                    }
                    sb.Append(text[pos++]);
                }
                return new Literal(sb.ToString());
            }
            if (pos < text.Length && (char.IsDigit(text[pos]) || text[pos] == '-'))
            {
                var start = pos++;
                while (pos < text.Length && (char.IsDigit(text[pos]) || text[pos] == '.')) pos++;
                var n = text[start..pos];
                return new Literal(n.Contains('.') ? new JValue(decimal.Parse(n, CultureInfo.InvariantCulture)) : new JValue(long.Parse(n, CultureInfo.InvariantCulture)));
            }
            var name = ParseIdentifier();
            switch (name)
            {
                case "true": return new Literal(true);
                case "false": return new Literal(false);
                case "null": return new Literal(JValue.CreateNull());
            }
            Expect('(');
            var args = new List<Node>();
            SkipSpace();
            if (!Peek(')'))
            {
                do { args.Add(ParseExpression()); SkipSpace(); } while (TryConsume(','));
            }
            Expect(')');
            return new Call(name, args);
        }

        private string ParseIdentifier()
        {
            SkipSpace();
            var start = pos;
            while (pos < text.Length && (char.IsLetterOrDigit(text[pos]) || text[pos] == '_' || text[pos] == '$')) pos++;
            if (start == pos) throw new FormatException($"expected a name at {pos} in {text}");
            return text[start..pos];
        }

        private void SkipSpace() { while (pos < text.Length && char.IsWhiteSpace(text[pos])) pos++; }
        private bool Peek(char c) => pos < text.Length && text[pos] == c;
        private bool TryConsume(char c) { SkipSpace(); if (!Peek(c)) return false; pos++; return true; }
        private void Expect(char c) { if (!TryConsume(c)) throw new FormatException($"expected '{c}' at {pos} in {text}"); }
    }
}

public interface IContext
{
    JToken TriggerBody { get; }
    DateTimeOffset UtcNow { get; }
    JToken Body(string action);
    JToken Outputs(string action);
}

public sealed class FlowExpressionException(string message) : Exception(message);
