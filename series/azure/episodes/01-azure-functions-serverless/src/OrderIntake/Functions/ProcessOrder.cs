using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;
using OrderIntake.Core;
using System.Text.Json;

namespace OrderIntake.Functions;

/// <summary>
/// Runs for every message on "orders". Throwing = the runtime retries the message
/// (maxDequeueCount, default 5) and then moves it to "orders-poison".
/// </summary>
public sealed class ProcessOrder(ICatalog catalog, ILogger<ProcessOrder> logger)
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { WriteIndented = true };

    // {OrderId} is read from the JSON message. That only works when the trigger parameter is a
    // POCO or a string, not an SDK type such as QueueMessage (see README, "gotchas").
    [Function(nameof(ProcessOrder))]
    [BlobOutput("orders-processed/{OrderId}.json", Connection = "OrdersStorage")]
    public string Run([QueueTrigger("orders", Connection = "OrdersStorage")] OrderMessage order,
        FunctionContext context)
    {
        context.BindingContext.BindingData.TryGetValue("DequeueCount", out var attempt);
        return Handle(order, attempt?.ToString() ?? "?");
    }

    public string Handle(OrderMessage order, string attempt)
    {
        logger.LogInformation("Pricing order {OrderId}, attempt {Attempt}", order.OrderId, attempt);
        var priced = Pricing.Price(order, catalog);   // UnknownSkuException -> retry -> poison

        logger.LogInformation("Order {OrderId} total {Total} EUR", priced.OrderId, priced.Total);
        return JsonSerializer.Serialize(priced, Json); // same blob name on a retry: overwrite, not duplicate
    }
}
