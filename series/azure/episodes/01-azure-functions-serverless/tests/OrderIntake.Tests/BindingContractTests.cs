using Microsoft.Azure.Functions.Worker;
using OrderIntake.Functions;
using System.Reflection;

namespace OrderIntake.Tests;

/// <summary>
/// The queue name, the blob path and the connection name are a contract between three functions
/// and the Bicep file. A rename in one place and not the other only fails at runtime, so pin them here.
/// </summary>
public class BindingContractTests
{
    private const string Connection = "OrdersStorage";

    private static T Attr<T>(MemberInfo m) where T : Attribute => m.GetCustomAttribute<T>()!;
    private static T Attr<T>(ParameterInfo p) where T : Attribute => p.GetCustomAttribute<T>()!;
    private static ParameterInfo Param(Type t) => t.GetMethod("Run")!.GetParameters()[0];

    [Fact]
    public void SubmitOrder_is_POST_orders_with_a_function_key()
    {
        var http = Attr<HttpTriggerAttribute>(Param(typeof(SubmitOrder)));
        Assert.Equal("orders", http.Route);
        Assert.Equal(["post"], http.Methods ?? []);
        Assert.Equal(AuthorizationLevel.Function, http.AuthLevel);
    }

    [Fact]
    public void SubmitOrder_writes_to_the_queue_that_ProcessOrder_reads()
    {
        var output = Attr<QueueOutputAttribute>(typeof(SubmitOrderOutput).GetProperty(nameof(SubmitOrderOutput.Messages))!);
        var trigger = Attr<QueueTriggerAttribute>(Param(typeof(ProcessOrder)));
        Assert.Equal(output.QueueName, trigger.QueueName);
        Assert.Equal(Connection, output.Connection);
        Assert.Equal(Connection, trigger.Connection);
    }

    [Fact]
    public void OrderPoison_listens_on_the_poison_queue_name_the_runtime_uses()
    {
        var trigger = Attr<QueueTriggerAttribute>(Param(typeof(OrderPoison)));
        Assert.Equal("orders-poison", trigger.QueueName);   // <queue>-poison
        Assert.Equal(Connection, trigger.Connection);
    }

    [Fact]
    public void ProcessOrder_names_the_blob_after_the_order_id()
    {
        var blob = Attr<BlobOutputAttribute>(typeof(ProcessOrder).GetMethod("Run")!);
        Assert.Equal("orders-processed/{OrderId}.json", blob.BlobPath);
        Assert.Equal(Connection, blob.Connection);
        // {OrderId} must match a property of the queue message
        Assert.NotNull(typeof(OrderIntake.Core.OrderMessage).GetProperty("OrderId"));
    }

    [Fact]
    public void ProcessOrder_trigger_is_a_POCO_so_JSON_binding_expressions_work()
    {
        // Binding expressions on JSON payload properties can't be used with SDK types (QueueMessage).
        Assert.Equal(typeof(OrderIntake.Core.OrderMessage), Param(typeof(ProcessOrder)).ParameterType);
    }
}
