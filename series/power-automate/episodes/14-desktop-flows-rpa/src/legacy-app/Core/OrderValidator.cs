using System.Globalization;

namespace ContosoPurchasing;

public sealed record ValidationResult(bool IsValid, IReadOnlyList<string> Errors, decimal Amount);

/// <summary>Validation the legacy form applies before it saves. The amount is parsed with the culture of the machine,
/// like a typical Windows desktop application: "1800,50" is 1800.50 on pt-PT and 180050 on en-US.</summary>
public static class OrderValidator
{
    public const decimal MaxAmount = 100_000m;
    public const int MaxSupplierLength = 60;

    public static ValidationResult Validate(string? supplier, string? description, string? amountText, CultureInfo culture)
    {
        var errors = new List<string>();
        if (string.IsNullOrWhiteSpace(supplier)) errors.Add("Supplier is required");
        else if (supplier.Trim().Length > MaxSupplierLength) errors.Add($"Supplier is longer than {MaxSupplierLength} characters");
        if (string.IsNullOrWhiteSpace(description)) errors.Add("Description is required");

        decimal amount = 0;
        if (!decimal.TryParse(amountText, NumberStyles.Number, culture, out amount)) errors.Add("Amount is not a number");
        else if (amount <= 0) errors.Add("Amount must be greater than zero");
        else if (amount > MaxAmount) errors.Add($"Amount is above the limit of {MaxAmount:0}");
        return new ValidationResult(errors.Count == 0, errors, amount);
    }
}
