using System;
using Microsoft.Xrm.Sdk;

namespace MGLab.Plugins
{
    /// <summary>
    /// Register on mgl_projectrequest — Create and Update, PreOperation (stage 20), synchronous.
    /// Update step: filtering attributes mgl_budget, mgl_priority, mgl_requeststatus, mgl_departmentid, mgl_duedate,
    /// pre-image "PreImage" with the same columns.
    /// </summary>
    public sealed class ProjectRequestValidationPlugin : PluginBase
    {
        public const string PreImageName = "PreImage";

        protected override void ExecuteCore(LocalContext local)
        {
            var target = local.Target;
            if (target == null || target.LogicalName != "mgl_projectrequest") return;

            var preImage = local.Context.MessageName == "Update" ? local.PreImage(PreImageName) : null;
            ProjectRequestRules.Apply(target, preImage, local.Tracing, DateTime.UtcNow);
        }
    }
}
