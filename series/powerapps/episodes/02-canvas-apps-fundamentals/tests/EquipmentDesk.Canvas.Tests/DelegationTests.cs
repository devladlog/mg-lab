using System.Text.RegularExpressions;
using Xunit;

namespace EquipmentDesk.Canvas.Tests;

/// <summary>
/// The interpreter can't tell us what Dataverse will delegate, so this is a lint: the gallery's Items formula may only
/// use functions that Microsoft Learn lists as delegable to Dataverse ("Power Apps delegable functions and operations
/// for Dataverse"). Anything else risks silently working on the first 500 rows only.
/// </summary>
public class DelegationTests
{
    private static readonly CanvasSource Source = new();

    // From the Learn table for Dataverse (text, choice and date columns). Text(), Len(), Trim() are explicitly NOT delegable.
    private static readonly HashSet<string> Delegable = ["Filter", "Search", "LookUp", "First", "Sort", "SortByColumns", "StartsWith", "IsBlank", "And", "Or", "Not", "CountRows", "CountIf"];

    internal static IEnumerable<string> Functions(string formula) =>
        // Drop 'quoted names' and "text" first, so 'Status (Equipment)' isn't mistaken for a call.
        Regex.Matches(Regex.Replace(formula, @"'[^']*'|""[^""]*""", "x"), @"\b([A-Z][A-Za-z]+)\s*\(").Select(m => m.Groups[1].Value).Distinct();

    [Fact]
    public void Gallery_Items_uses_only_functions_Dataverse_can_delegate()
    {
        var used = Functions(Source.Formula("galEquipment", "Items")).ToArray();
        Assert.Equal(new[] { "Sort", "Filter", "StartsWith" }, used);
        Assert.All(used, f => Assert.Contains(f, Delegable));
    }

    [Theory]
    [InlineData("Filter(Loans, Text('Loan date', \"yyyy-mm\") = \"2026-11\")", "Text")]
    [InlineData("Filter(Equipment, Len('Asset tag') > 0)", "Len")]
    [InlineData("Filter(Equipment, Lower(Name) = \"dock\")", "Lower")]
    public void The_lint_catches_common_non_delegable_formulas(string formula, string offender)
    {
        Assert.Contains(offender, Functions(formula).Where(f => !Delegable.Contains(f)));
    }
}
