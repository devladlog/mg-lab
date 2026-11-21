using System;
using Microsoft.Xrm.Sdk;

namespace MGLab.D365.Plugins
{
    /// <summary>
    /// Resolves the services every plug-in needs, traces the call and turns unexpected exceptions into a traced
    /// InvalidPluginExecutionException. Plug-in instances are cached and shared by the platform: no mutable fields.
    /// </summary>
    public abstract class PluginBase : IPlugin
    {
        public void Execute(IServiceProvider serviceProvider)
        {
            if (serviceProvider == null) throw new ArgumentNullException(nameof(serviceProvider));

            var context = (IPluginExecutionContext)serviceProvider.GetService(typeof(IPluginExecutionContext));
            var tracing = (ITracingService)serviceProvider.GetService(typeof(ITracingService));
            var factory = (IOrganizationServiceFactory)serviceProvider.GetService(typeof(IOrganizationServiceFactory));

            tracing.Trace($"{GetType().Name}: {context.MessageName} {context.PrimaryEntityName} " +
                          $"stage {context.Stage} mode {context.Mode} depth {context.Depth}");
            try
            {
                ExecuteCore(new LocalContext(context, tracing, factory));
            }
            catch (InvalidPluginExecutionException)
            {
                throw; // business errors: shown to the caller as they are
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

        /// <summary>Service that runs as the user the step runs as (the caller unless the step impersonates).</summary>
        public IOrganizationService UserService => Factory.CreateOrganizationService(Context.UserId);

        public Entity PostImage(string name) =>
            Context.PostEntityImages.Contains(name) ? Context.PostEntityImages[name] : null;
    }

    /// <summary>Names shared by both plug-ins and by the Python deploy tool (plugins.json).</summary>
    public static class ProjectRequest
    {
        public const string Table = "mgl_projectrequest";
        public const string Id = "mgl_projectrequestid";
        public const string Budget = "mgl_budget";
        public const string DueDate = "mgl_duedate";
        public const string Justification = "mgl_justification";   // episode 3
        public const string Account = "mgl_customeraccountid";      // episode 1
        public const string RiskScore = "mgl_riskscore";            // added by this episode
        public const string StateCode = "statecode";
    }
}
