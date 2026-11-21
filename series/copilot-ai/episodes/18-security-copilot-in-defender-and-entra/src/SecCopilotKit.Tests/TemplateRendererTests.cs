using Kusto.Language;
using Kusto.Language.Syntax;
using Xunit;

namespace Contoso.SecCopilotKit.Tests;

public class TemplateRendererTests
{
    private const string Template = "EmailEvents | where Timestamp > ago(7d) | where SenderFromDomain =~ '{{domain}}' | take 10";
    private const string Hostile = "x' or 1==1 | where 'a'=='a";

    private static int Operators(string kql) => KustoCode.Parse(kql).Syntax.GetDescendants<QueryOperator>().Count;
    private static IReadOnlyDictionary<string, string> V(string v) => new Dictionary<string, string> { ["domain"] = v };

    [Fact] public void FindsPlaceholdersOnce() =>
        Assert.Equal(new[] { "a", "b" }, TemplateRenderer.Placeholders("x '{{a}}' '{{ b }}' '{{a}}'"));

    [Fact] public void RendersAValue() =>
        Assert.Contains("'contoso.example'", TemplateRenderer.Render(Template, V("contoso.example")));

    [Fact] public void MissingValueThrows() =>
        Assert.Throws<KeyNotFoundException>(() => TemplateRenderer.Render(Template, new Dictionary<string, string>()));

    [Theory]
    [InlineData("a'b", "a\\'b")]
    [InlineData("a\\b", "a\\\\b")]
    [InlineData("a\"b", "a\\\"b")]
    [InlineData("a\nb", "a\\nb")]
    [InlineData("plain", "plain")]
    public void EscapesTheCharactersThatEndAString(string input, string expected) =>
        Assert.Equal(expected, TemplateRenderer.EscapeLiteral(input));

    [Fact] public void EscapedHostileInputKeepsTheQueryShape()
    {
        var clean = TemplateRenderer.Render(Template, V("contoso.example"));
        var rendered = TemplateRenderer.Render(Template, V(Hostile));
        Assert.Equal(Operators(clean), Operators(rendered));
        Assert.DoesNotContain(KustoCode.ParseAndAnalyze(rendered, HuntingSchema.Globals).GetDiagnostics(), d => d.Severity == "Error");
    }

    [Fact] public void UnescapedHostileInputChangesTheQuery()
    {
        // The reason for the rule: without escaping, the input adds operators to the query.
        var clean = TemplateRenderer.Render(Template, V("contoso.example"));
        var broken = TemplateRenderer.Render(Template, V(Hostile), escape: false);
        Assert.NotEqual(Operators(clean), Operators(broken));
    }

    [Fact] public void EscapedValueStaysOneStringLiteral()
    {
        var rendered = TemplateRenderer.Render(Template, V(Hostile));
        var literals = KustoCode.Parse(rendered).GetLexicalTokens().Count(t => t.Kind == SyntaxKind.StringLiteralToken);
        Assert.Equal(1, literals);
    }
}
