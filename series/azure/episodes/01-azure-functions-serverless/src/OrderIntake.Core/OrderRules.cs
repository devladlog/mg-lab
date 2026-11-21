using System.Text.RegularExpressions;

namespace OrderIntake.Core;

/// <summary>
/// Shape checks only: cheap, synchronous, no I/O. They run in the HTTP function so a bad
/// request gets a 400 straight away and never reaches the queue.
/// </summary>
public static partial class OrderRules
{
    public const int MaxLines = 20;
    public const int MaxQuantity = 100;

    [GeneratedRegex("^[A-Z]{3}-[0-9]{3}$")]
    private static partial Regex SkuPattern();

    public static IReadOnlyList<string> Validate(OrderRequest? order)
    {
        if (order is null) return ["Body must be a JSON order."];

        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(order.CustomerId))
            errors.Add("customerId is required.");

        if (order.Lines is null || order.Lines.Count == 0)
        {
            errors.Add("At least one line is required.");
            return errors;
        }

        if (order.Lines.Count > MaxLines)
            errors.Add($"An order can have at most {MaxLines} lines.");

        for (var i = 0; i < order.Lines.Count; i++)
        {
            var line = order.Lines[i];
            if (line is null) { errors.Add($"lines[{i}] is empty."); continue; }
            if (string.IsNullOrWhiteSpace(line.Sku) || !SkuPattern().IsMatch(line.Sku))
                errors.Add($"lines[{i}].sku must look like ABC-123.");
            if (line.Quantity < 1 || line.Quantity > MaxQuantity)
                errors.Add($"lines[{i}].quantity must be between 1 and {MaxQuantity}.");
        }

        var duplicates = order.Lines.Where(l => l?.Sku is not null)
            .GroupBy(l => l.Sku).Where(g => g.Count() > 1).Select(g => g.Key);
        foreach (var sku in duplicates)
            errors.Add($"SKU {sku} appears more than once; merge the lines.");

        return errors;
    }
}
