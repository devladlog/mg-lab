using System;
using System.Collections.Generic;
using Microsoft.Xrm.Sdk;
using Moq;

namespace MGLab.Plugins.Tests
{
    /// <summary>Builds a fake IServiceProvider the way Dataverse would pass it to a plug-in.</summary>
    internal sealed class PluginTestContext
    {
        public ParameterCollection InputParameters { get; } = new ParameterCollection();
        public EntityImageCollection PreImages { get; } = new EntityImageCollection();
        public List<string> Traces { get; } = new List<string>();
        public bool BrokenPreImages { get; set; }

        public IServiceProvider Build(string message, Entity target, Entity preImage = null)
        {
            InputParameters["Target"] = target;
            if (preImage != null) PreImages[ProjectRequestValidationPlugin.PreImageName] = preImage;

            var context = new Mock<IPluginExecutionContext>();
            context.Setup(c => c.MessageName).Returns(message);
            context.Setup(c => c.PrimaryEntityName).Returns(target.LogicalName);
            context.Setup(c => c.Stage).Returns(20);
            context.Setup(c => c.Depth).Returns(1);
            context.Setup(c => c.InputParameters).Returns(InputParameters);
            context.Setup(c => c.PreEntityImages).Returns(BrokenPreImages ? null : PreImages);

            var tracing = new Mock<ITracingService>();
            tracing.Setup(t => t.Trace(It.IsAny<string>(), It.IsAny<object[]>()))
                   .Callback<string, object[]>((f, a) => Traces.Add(a?.Length > 0 ? string.Format(f, a) : f));

            var provider = new Mock<IServiceProvider>();
            provider.Setup(p => p.GetService(typeof(IPluginExecutionContext))).Returns(context.Object);
            provider.Setup(p => p.GetService(typeof(ITracingService))).Returns(tracing.Object);
            provider.Setup(p => p.GetService(typeof(IOrganizationServiceFactory))).Returns(new Mock<IOrganizationServiceFactory>().Object);
            return provider.Object;
        }
    }
}
