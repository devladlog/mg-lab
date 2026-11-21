using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;
using OrderIntake.Core;
using OrderIntake.Functions;
using System.Text;
using System.Text.Json;

namespace OrderIntake.Tests;

/// <summary>The function classes are plain classes: call Run() directly, no host needed.</summary>
public class FunctionTests
{
    private static readonly DateTimeOffset Now = new(2026, 11, 21, 10, 0, 0, TimeSpan.Zero);

    private static HttpRequest Post(string body, string contentType = "application/json")
    {
        var ctx = new DefaultHttpContext();
        ctx.Request.Method = "POST";
        ctx.Request.ContentType = contentType;
        ctx.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(body));
        return ctx.Request;
    }

    private static SubmitOrder Submit() => new(new FixedClock(Now), NullLogger<SubmitOrder>.Instance);

    [Fact]
    public async Task Valid_order_returns_202_and_one_queue_message()
    {
        var output = await Submit().Run(Post("""{"customerId":"C-1001","lines":[{"sku":"DOC-100","quantity":2}]}"""));

        var accepted = Assert.IsType<AcceptedResult>(output.Result);
        Assert.Equal(202, accepted.StatusCode);
        var message = Assert.Single(output.Messages);
        Assert.Equal("C-1001", message.CustomerId);
        Assert.Equal(Now, message.ReceivedAt);
        Assert.Equal(32, message.OrderId.Length);
    }

    [Fact]
    public async Task Invalid_order_returns_400_and_nothing_is_queued()
    {
        var output = await Submit().Run(Post("""{"customerId":"","lines":[{"sku":"bad","quantity":0}]}"""));

        var bad = Assert.IsType<BadRequestObjectResult>(output.Result);
        Assert.Contains("customerId is required.", JsonSerializer.Serialize(bad.Value));
        Assert.Empty(output.Messages);
    }

    [Fact]
    public async Task Malformed_json_returns_400()
    {
        var output = await Submit().Run(Post("{ not json"));
        Assert.IsType<BadRequestObjectResult>(output.Result);
        Assert.Empty(output.Messages);
    }

    [Fact]
    public async Task Wrong_content_type_returns_415()
    {
        var output = await Submit().Run(Post("customerId=C-1001", "application/x-www-form-urlencoded"));
        Assert.IsType<UnsupportedMediaTypeResult>(output.Result);
        Assert.Empty(output.Messages);
    }

    [Fact]
    public void ProcessOrder_writes_the_priced_order_as_json()
    {
        var msg = new OrderMessage("abc", "C-1001", [new("KEY-010", 2)], Now);

        var json = new ProcessOrder(new InMemoryCatalog(), NullLogger<ProcessOrder>.Instance).Handle(msg, "1");

        using var doc = JsonDocument.Parse(json);
        Assert.Equal("abc", doc.RootElement.GetProperty("orderId").GetString());
        Assert.Equal(99.00m, doc.RootElement.GetProperty("total").GetDecimal());
    }

    [Fact]
    public void ProcessOrder_throws_on_unknown_sku_so_the_message_is_retried()
    {
        var msg = new OrderMessage("abc", "C-1001", [new("ZZZ-999", 1)], Now);

        Assert.Throws<UnknownSkuException>(() =>
            new ProcessOrder(new InMemoryCatalog(), NullLogger<ProcessOrder>.Instance).Handle(msg, "1"));
    }

    private sealed class FixedClock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}
