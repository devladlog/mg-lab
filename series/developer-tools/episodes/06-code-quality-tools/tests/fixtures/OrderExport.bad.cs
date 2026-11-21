using System.Text;
using System.Globalization;
using Microsoft.EntityFrameworkCore;

namespace Contoso.Orders.Api
{
    public static class OrderExport
    {
        static int exported;

        public static async Task<string> ToCsvAsync(OrdersDb db, CancellationToken cancellationToken)
        {
            var sb = new StringBuilder();
            foreach (var o in await db.Orders.AsNoTracking().ToListAsync())
            {
                  sb.AppendLine(o.Customer + ";" + o.Total.ToString("N2"));
            }
            return sb.ToString();
        }
    }
}
