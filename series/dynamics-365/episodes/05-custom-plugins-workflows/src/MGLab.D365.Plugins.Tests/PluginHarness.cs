using Microsoft.Xrm.Sdk;
using Moq;

namespace MGLab.D365.Plugins.Tests;

/// <summary>Builds the IServiceProvider a plug-in receives, with Moq. Collects trace lines.</summary>
public sealed class PluginHarness
{
    public Mock<IPluginExecutionContext> Context { get; } = new();
    public Mock<IOrganizationService> Service { get; } = new();
    public List<string> Traces { get; } = new();
    public ParameterCollection Inputs { get; } = new();
    public ParameterCollection Outputs { get; } = new();
    public EntityImageCollection PostImages { get; } = new();
    public Guid UserId { get; } = new("00000000-0000-0000-0000-0000000000a1");

    public PluginHarness(string message, string entity, int stage, int mode, Guid primaryId, int depth = 1)
    {
        Context.SetupGet(c => c.MessageName).Returns(message);
        Context.SetupGet(c => c.PrimaryEntityName).Returns(entity);
        Context.SetupGet(c => c.PrimaryEntityId).Returns(primaryId);
        Context.SetupGet(c => c.Stage).Returns(stage);
        Context.SetupGet(c => c.Mode).Returns(mode);
        Context.SetupGet(c => c.Depth).Returns(depth);
        Context.SetupGet(c => c.UserId).Returns(UserId);
        Context.SetupGet(c => c.InputParameters).Returns(Inputs);
        Context.SetupGet(c => c.OutputParameters).Returns(Outputs);
        Context.SetupGet(c => c.PostEntityImages).Returns(PostImages);
        Context.SetupGet(c => c.PreEntityImages).Returns(new EntityImageCollection());
    }

    public void Run(IPlugin plugin)
    {
        var tracing = new Mock<ITracingService>();
        tracing.Setup(t => t.Trace(It.IsAny<string>(), It.IsAny<object[]>()))
               .Callback<string, object[]>((f, a) => Traces.Add(a is { Length: > 0 } ? string.Format(f, a) : f));
        var factory = new Mock<IOrganizationServiceFactory>();
        factory.Setup(f => f.CreateOrganizationService(UserId)).Returns(Service.Object);

        var provider = new Mock<IServiceProvider>();
        provider.Setup(p => p.GetService(typeof(IPluginExecutionContext))).Returns(Context.Object);
        provider.Setup(p => p.GetService(typeof(ITracingService))).Returns(tracing.Object);
        provider.Setup(p => p.GetService(typeof(IOrganizationServiceFactory))).Returns(factory.Object);
        plugin.Execute(provider.Object);
    }
}
