using System;
using Microsoft.Xrm.Sdk;

namespace MGLab.Plugins
{
    /// <summary>
    /// Small base class: resolves the services every plug-in needs and turns unexpected
    /// exceptions into a traced InvalidPluginExecutionException.
    /// </summary>
    public abstract class PluginBase : IPlugin
    {
        public void Execute(IServiceProvider serviceProvider)
        {
            if (serviceProvider == null) throw new ArgumentNullException(nameof(serviceProvider));

            var context = (IPluginExecutionContext)serviceProvider.GetService(typeof(IPluginExecutionContext));
            var tracing = (ITracingService)serviceProvider.GetService(typeof(ITracingService));
            var factory = (IOrganizationServiceFactory)serviceProvider.GetService(typeof(IOrganizationServiceFactory));

            tracing.Trace($"{GetType().Name}: {context.MessageName} {context.PrimaryEntityName} stage {context.Stage} depth {context.Depth}");

            try
            {
                ExecuteCore(new LocalContext(context, tracing, factory));
            }
            catch (InvalidPluginExecutionException)
            {
                throw; // business errors: shown to the user as-is
            }
            catch (Exception ex)
            {
                tracing.Trace($"Unexpected error: {ex}");
                throw new InvalidPluginExecutionException($"{GetType().Name} failed. See the plug-in trace log.", ex);
            }
        }

        protected abstract void ExecuteCore(LocalContext local);
    }

    public sealed class LocalContext
    {
        public LocalContext(IPluginExecutionContext context, ITracingService tracing, IOrganizationServiceFactory factory)
        {
            Context = context;
            Tracing = tracing;
            Factory = factory;
        }

        public IPluginExecutionContext Context { get; }
        public ITracingService Tracing { get; }
        public IOrganizationServiceFactory Factory { get; }

        public Entity Target =>
            Context.InputParameters.Contains("Target") ? Context.InputParameters["Target"] as Entity : null;

        public Entity PreImage(string name) =>
            Context.PreEntityImages.Contains(name) ? Context.PreEntityImages[name] : null;
    }
}
