using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Contoso.Orders.Api.Tests;

public class OrderExportTests(ApiFactory factory) : IClassFixture<ApiFactory>
{
    [Fact]
    public async Task Csv_has_one_line_per_order_with_the_same_number_format_on_every_machine()
    {
        using var scope = factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrdersDb>();

        var csv = await OrderExport.ToCsvAsync(db, CancellationToken.None);

        var lines = csv.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        Assert.Equal(await db.Orders.CountAsync(), lines.Length);
        Assert.Matches(@"^[^;]+;[\d,]+\.\d{2}$", lines[0]);
    }
}
