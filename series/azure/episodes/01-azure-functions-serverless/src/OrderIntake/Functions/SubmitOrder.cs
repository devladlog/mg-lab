using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;
using OrderIntake.Core;
using System.Text.Json;

namespace OrderIntake.Functions;

/// <summary>POST /api/orders: validate, answer 202 fast, hand the work to a queue.</summary>
public sealed class SubmitOrder(TimeProvider clock, ILogger<SubmitOrder> logger)
{
    [Function(nameof(SubmitOrder))]
    public async Task<SubmitOrderOutput> Run(
        [HttpTrigger(AuthorizationLevel.Function, "post", Route = "orders")] HttpRequest req)
    {
        if (!req.HasJsonContentType())
            return Reply(new UnsupportedMediaTypeResult());

        OrderRequest? order;
        try { order = await req.ReadFromJsonAsync<OrderRequest>(); }
        catch (JsonException) { order = null; }

        var errors = OrderRules.Validate(order);
        if (errors.Count > 0)
            return Reply(new BadRequestObjectResult(new { errors }));

        var message = new OrderMessage(Guid.NewGuid().ToString("N"), order!.CustomerId,
            order.Lines, clock.GetUtcNow());
        logger.LogInformation("Order {OrderId} accepted for {CustomerId} ({Lines} lines)",
            message.OrderId, message.CustomerId, message.Lines.Count);

        return new SubmitOrderOutput
        {
            Result = new AcceptedResult((string?)null, new { orderId = message.OrderId }),
            Messages = [message],   // one message on the "orders" queue
        };
    }

    private static SubmitOrderOutput Reply(IActionResult result) => new() { Result = result };
}

/// <summary>
/// Two outputs from one function: the HTTP response and the queue messages. An array output writes one
/// message per element, so the empty default means "nothing queued" for a 400 or 415.
/// </summary>
public sealed class SubmitOrderOutput
{
    [HttpResult]
    public required IActionResult Result { get; init; }

    [QueueOutput("orders", Connection = "OrdersStorage")]
    public OrderMessage[] Messages { get; init; } = [];
}
