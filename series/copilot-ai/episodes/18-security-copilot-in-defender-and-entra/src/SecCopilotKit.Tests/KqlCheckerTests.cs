using Xunit;

namespace Contoso.SecCopilotKit.Tests;

public class KqlCheckerTests
{
    private static IReadOnlyList<Finding> F(string kql, string target = "Defender") => KqlChecker.Check(kql, "t", target).Findings;

    private const string Good = "EntraIdSignInEvents | where Timestamp > ago(7d) | where AccountUpn =~ '{{upn}}' | summarize n = count() by AccountUpn";

    [Fact] public void GoodQueryHasNoFindings() => Assert.Empty(F(Good));

    [Fact] public void UnknownColumnIsAnError() =>
        Assert.Contains(F("EmailEvents | where Timestamp > ago(1d) | where SenderAddress == 'a' | take 5"), f => f.Severity == Severity.Error && f.Message.Contains("SenderAddress"));

    [Fact] public void ColumnNamesAreCaseSensitive() =>
        Assert.Contains(F("EntraIdSignInEvents | where Timestamp > ago(1d) | where AccountUPN == 'a' | take 5"), f => f.Severity == Severity.Error);

    [Fact] public void SyntaxErrorIsAnError() =>
        Assert.Contains(F("EmailEvents | where | take 5"), f => f.Severity == Severity.Error);

    [Fact] public void PlaceholderInsideStringIsAccepted() => Assert.DoesNotContain(F(Good), f => f.Severity == Severity.Error);

    [Fact] public void PlaceholderOutsideStringIsAnError() =>
        Assert.Contains(F("EmailEvents | where Timestamp > ago(1d) | where Subject == {{s}} | take 5"), f => f.Message.Contains("outside a string literal"));

    [Fact] public void PlaceholderInsideDoubleQuotesIsAccepted() =>
        Assert.DoesNotContain(F("EmailEvents | where Timestamp > ago(1d) | where Subject has \"{{s}}\" | take 5"), f => f.Message.Contains("outside"));

    [Fact] public void PlaceholderInTheMiddleOfAStringIsAccepted() =>
        Assert.DoesNotContain(F("EmailEvents | where Timestamp > ago(1d) | where RecipientEmailAddress endswith '@{{d}}' | take 5"), f => f.Message.Contains("outside"));

    [Fact] public void OldTableNameWarnsAndStillAnalyses()
    {
        var r = F("AADSignInEventsBeta | where Timestamp > ago(1d) | take 5");
        Assert.Contains(r, f => f.Severity == Severity.Warning && f.Message.Contains("EntraIdSignInEvents"));
        Assert.DoesNotContain(r, f => f.Severity == Severity.Error);
    }

    [Fact] public void UnboundedQueryWarns() =>
        Assert.Contains(F("EmailEvents | where Timestamp > ago(1d) | project Subject"), f => f.Message.Contains("not bounded"));

    [Theory]
    [InlineData("| take 10")]
    [InlineData("| top 10 by Timestamp desc")]
    [InlineData("| summarize n = count() by Subject")]
    [InlineData("| count")]
    public void BoundingOperatorsSatisfyTheRule(string tail) =>
        Assert.DoesNotContain(F("EmailEvents | where Timestamp > ago(1d) " + tail), f => f.Message.Contains("not bounded"));

    [Fact] public void MissingTimeFilterWarns() =>
        Assert.Contains(F("EmailEvents | take 5"), f => f.Message.Contains("time filter"));

    [Fact] public void BetweenCountsAsTimeFilter() =>
        Assert.DoesNotContain(F("EmailEvents | where Timestamp between (ago(2d) .. ago(1d)) | take 5"), f => f.Message.Contains("time filter"));

    [Fact] public void TemplateOverTheLimitIsAnError() =>
        Assert.Contains(KqlChecker.Check("EmailEvents | take 1 // " + new string('x', 80_001), "t").Findings, f => f.Message.Contains("limit is 80000"));

    [Fact] public void OtherTargetsAreSyntaxCheckedOnly()
    {
        var r = KqlChecker.Check("SigninLogs | where TimeGenerated > ago(1d) | take 5", "t", "Sentinel");
        Assert.False(r.SchemaChecked);
        Assert.DoesNotContain(r.Findings, f => f.Severity == Severity.Error);
        Assert.Contains(r.Findings, f => f.Severity == Severity.Info);
    }

    [Fact] public void ResultColumnsFollowTheProjection()
    {
        var r = KqlChecker.Check("EmailEvents | where Timestamp > ago(1d) | project Subject, RecipientEmailAddress | take 3", "t");
        Assert.Equal(new[] { "Subject", "RecipientEmailAddress" }, r.ResultColumns);
    }

    [Theory]
    [InlineData("EmailEvents", "SenderFromDomain")]
    [InlineData("EntraIdSignInEvents", "AccountUpn")]
    [InlineData("AlertInfo", "AttackTechniques")]
    public void SchemaTablesHaveTheLearnColumns(string table, string column)
    {
        var r = KqlChecker.Check($"{table} | where Timestamp > ago(1d) | project {column} | take 1", "t");
        Assert.Empty(r.Findings);
    }
}
