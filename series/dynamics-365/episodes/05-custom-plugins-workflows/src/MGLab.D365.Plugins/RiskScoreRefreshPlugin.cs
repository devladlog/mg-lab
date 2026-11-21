using Microsoft.Xrm.Sdk;

namespace MGLab.D365.Plugins
{
    /// <summary>
    /// Asynchronous, post-operation, on Create and Update of mgl_projectrequest (filtering attributes: budget,
    /// due date, justification, customer account). Calls the custom API and stores the score in mgl_riskscore,
    /// so views, charts and flows can use it. This is the job a classic background workflow used to do.
    /// </summary>
    public sealed class RiskScoreRefreshPlugin : PluginBase
    {
        public const string PostImageName = "PostImage";
        public const int PostOperation = 40;
        public const int Asynchronous = 1;

        protected override void ExecuteCore(LocalContext local)
        {
            var ctx = local.Context;
            if (ctx.Stage != PostOperation || ctx.Mode != Asynchronous)
            {
                local.Tracing.Trace("Registered with the wrong stage or mode: expected post-operation, asynchronous.");
                return;
            }

            var service = local.UserService;
            var request = new OrganizationRequest(AssessProjectRequestApi.MessageName)
            {
                ["Target"] = new EntityReference(ProjectRequest.Table, ctx.PrimaryEntityId),
            };
            var response = service.Execute(request);
            var score = (int)response["RiskScore"];

            // The post-image says what the column held when the save happened. Writing the same value again
            // would still count as an update, and a flow filtering on mgl_riskscore would run for nothing.
            var current = local.PostImage(PostImageName)?.GetAttributeValue<int?>(ProjectRequest.RiskScore);
            if (current == score)
            {
                local.Tracing.Trace($"Risk score unchanged ({score}); no update.");
                return;
            }

            // Only the one column: mgl_riskscore is not a filtering attribute of this step, so no loop.
            service.Update(new Entity(ProjectRequest.Table, ctx.PrimaryEntityId) { [ProjectRequest.RiskScore] = score });
            local.Tracing.Trace($"Risk score {current?.ToString() ?? "(empty)"} -> {score} ({response["RiskLevel"]}).");
        }
    }
}
