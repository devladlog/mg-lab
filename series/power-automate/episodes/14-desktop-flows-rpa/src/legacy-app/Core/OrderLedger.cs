using System.Globalization;
using System.Text;

namespace ContosoPurchasing;

public sealed record PurchaseOrder(string OrderNo, DateTimeOffset SavedAt, string Supplier, string Description,
                                   decimal Amount, string EnteredBy);

/// <summary>The legacy system's only "database": a CSV ledger. No API, which is why the process needs a desktop flow.</summary>
public sealed class OrderLedger
{
    public const string Header = "OrderNo,SavedAtUtc,Supplier,Description,Amount,EnteredBy";
    private readonly string _path;

    public OrderLedger(string path) => _path = path;

    public static string DefaultPath() =>
        Environment.GetEnvironmentVariable("CONTOSO_LEGACY_LEDGER")
        ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ContosoLegacy", "orders.csv");

    public IReadOnlyList<PurchaseOrder> ReadAll()
    {
        if (!File.Exists(_path)) return Array.Empty<PurchaseOrder>();
        var orders = new List<PurchaseOrder>();
        foreach (var line in File.ReadLines(_path, Encoding.UTF8).Skip(1).Where(l => l.Length > 0))
        {
            var f = SplitCsv(line);
            orders.Add(new PurchaseOrder(f[0], DateTimeOffset.Parse(f[1], CultureInfo.InvariantCulture), f[2], f[3],
                decimal.Parse(f[4], CultureInfo.InvariantCulture), f[5]));
        }
        return orders;
    }

    public PurchaseOrder Append(string supplier, string description, decimal amount, string enteredBy, DateTimeOffset now)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(_path))!);
        var existing = ReadAll();
        var year = now.UtcDateTime.Year;
        var next = existing.Count(o => o.OrderNo.StartsWith($"PO-{year}-", StringComparison.Ordinal)) + 1;
        var order = new PurchaseOrder($"PO-{year}-{next:0000}", now, supplier.Trim(), description.Trim(), amount, enteredBy);
        var line = string.Join(",", Quote(order.OrderNo), Quote(order.SavedAt.UtcDateTime.ToString("o", CultureInfo.InvariantCulture)),
            Quote(order.Supplier), Quote(order.Description), order.Amount.ToString("0.00", CultureInfo.InvariantCulture), Quote(order.EnteredBy));
        if (!File.Exists(_path)) File.WriteAllText(_path, Header + Environment.NewLine, new UTF8Encoding(false));
        File.AppendAllText(_path, line + Environment.NewLine, new UTF8Encoding(false));
        return order;
    }

    private static string Quote(string s) => "\"" + s.Replace("\"", "\"\"") + "\"";

    internal static List<string> SplitCsv(string line)
    {
        var fields = new List<string>();
        var sb = new StringBuilder();
        bool quoted = false;
        for (int i = 0; i < line.Length; i++)
        {
            char c = line[i];
            if (quoted)
            {
                if (c == '"' && i + 1 < line.Length && line[i + 1] == '"') { sb.Append('"'); i++; }
                else if (c == '"') quoted = false;
                else sb.Append(c);
            }
            else if (c == '"') quoted = true;
            else if (c == ',') { fields.Add(sb.ToString()); sb.Clear(); }
            else sb.Append(c);
        }
        fields.Add(sb.ToString());
        return fields;
    }
}
