using System.Globalization;
using Contoso.Orders.Contracts;

// Checks a CSV of "customer,total" lines with the same rules the orders API enforces.
// The rules come from the Contoso.Orders.Contracts package, not from a copy of the code.
if (args.Length != 1)
{
    Console.Error.WriteLine("usage: OrdersReport <orders.csv>");
    return 2;
}

var invalid = 0;
foreach (var (line, number) in File.ReadLines(args[0]).Skip(1).Select((l, i) => (l, i + 2)))
{
    var parts = line.Split(',');
    var total = decimal.TryParse(parts.ElementAtOrDefault(1), NumberStyles.Number, CultureInfo.InvariantCulture, out var t) ? t : 0m;
    var errors = OrderRules.Validate(new NewOrder(parts[0], total));
    if (errors.Count == 0)
    {
        Console.WriteLine($"line {number}: ok");
        continue;
    }

    invalid++;
    Console.WriteLine($"line {number}: {string.Join("; ", errors.Select(e => $"{e.Key}: {e.Value[0]}"))}");
}

Console.WriteLine($"{invalid} invalid");
return invalid == 0 ? 0 : 1;
