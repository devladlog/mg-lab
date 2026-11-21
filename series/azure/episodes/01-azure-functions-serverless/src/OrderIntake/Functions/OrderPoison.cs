using Azure.Storage.Queues.Models;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.Logging;

namespace OrderIntake.Functions;

/// <summary>Nobody watches a poison queue by default. This turns it into an error log you can alert on.</summary>
public sealed class OrderPoison(ILogger<OrderPoison> logger)
{
    [Function(nameof(OrderPoison))]
    public void Run([QueueTrigger("orders-poison", Connection = "OrdersStorage")] QueueMessage message) =>
        logger.LogError("Order message {MessageId} failed 5 times and needs a human: {Body}",
            message.MessageId, message.Body.ToString());
}
