namespace Contoso.Orders.Contracts;

/// <summary>Body of <c>POST /orders</c>.</summary>
public sealed record NewOrder(string? Customer, decimal Total);

/// <summary>One page of a list endpoint.</summary>
public sealed record Page<T>(int PageNumber, int PageSize, int Total, IReadOnlyList<T> Items)
{
    public int TotalPages => Total == 0 ? 0 : (Total + PageSize - 1) / PageSize;
}

/// <summary>Paging rules shared by every list endpoint (episode 1's "feat(orders): add paging").</summary>
public static class Paging
{
    public const int DefaultPageSize = 50;
    public const int MaxPageSize = 100;

    public static (int Page, int Size)? Normalize(int? page, int? pageSize)
    {
        var p = page ?? 1;
        if (p < 1) return null;
        return (p, Math.Clamp(pageSize ?? DefaultPageSize, 1, MaxPageSize));
    }
}

/// <summary>The rules the API enforces on a new order. Clients can check them before sending.</summary>
public static class OrderRules
{
    public const int MaxCustomerLength = 100;

    /// <summary>Field name to messages; empty when the order is valid.</summary>
    public static IReadOnlyDictionary<string, string[]> Validate(NewOrder input)
    {
        var errors = new Dictionary<string, string[]>();
        if (string.IsNullOrWhiteSpace(input.Customer) || input.Customer.Length > MaxCustomerLength)
            errors["customer"] = [$"customer is required (max {MaxCustomerLength} characters)"];
        if (input.Total <= 0)
            errors["total"] = ["total must be greater than zero"];
        return errors;
    }
}
