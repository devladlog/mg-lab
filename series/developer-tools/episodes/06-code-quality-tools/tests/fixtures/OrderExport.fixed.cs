using System.Globalization;
using System.Text;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Api;

public static class OrderExport
{
    public static async Task<string> ToCsvAsync(OrdersDb db, CancellationToken cancellationToken)
    {
        var sb = new StringBuilder();
        foreach (var o in await db.Orders.AsNoTracking().ToListAsync(cancellationToken: cancellationToken))
        {
            sb.AppendLine(o.Customer + ";" + o.Total.ToString("N2", CultureInfo.InvariantCulture));
        }
        return sb.ToString();
    }
}
