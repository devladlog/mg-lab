using System;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;

namespace MGLab.D365.Plugins
{
    /// <summary>
    /// Main operation of the custom API <c>mgl_AssessProjectRequest</c> (an Action bound to mgl_projectrequest).
    /// Request: Target (EntityReference, created by the platform for Entity binding).
    /// Response: RiskScore (Integer), RiskLevel (String), Reasons (String).
    /// No step is registered for it: the custom API's PluginTypeId points to this class.
    /// </summary>
    public sealed class AssessProjectRequestApi : PluginBase
    {
        public const string MessageName = "mgl_AssessProjectRequest";
        public const int MainOperation = 30;
        public const int MaxOthersCounted = 50;

        private readonly Func<DateTime> _utcNow;

        public AssessProjectRequestApi() : this(() => DateTime.UtcNow) { }

        internal AssessProjectRequestApi(Func<DateTime> utcNow) { _utcNow = utcNow; }

        protected override void ExecuteCore(LocalContext local)
        {
            var ctx = local.Context;
            if (ctx.MessageName != MessageName || ctx.Stage != MainOperation)
            {
                local.Tracing.Trace($"Not registered as the main operation of {MessageName}; nothing to do.");
                return;
            }

            if (!(ctx.InputParameters.Contains("Target") && ctx.InputParameters["Target"] is EntityReference target)
                || target.LogicalName != ProjectRequest.Table)
                throw new InvalidPluginExecutionException($"{MessageName} needs a {ProjectRequest.Table} as Target.");

            var service = local.UserService;
            var record = service.Retrieve(ProjectRequest.Table, target.Id, new ColumnSet(
                ProjectRequest.Budget, ProjectRequest.DueDate, ProjectRequest.Justification, ProjectRequest.Account));

            var account = record.GetAttributeValue<EntityReference>(ProjectRequest.Account);
            var input = new RiskInput
            {
                Budget = record.GetAttributeValue<Money>(ProjectRequest.Budget)?.Value,
                DueDate = ProjectRisk.NearestDate(record.GetAttributeValue<DateTime?>(ProjectRequest.DueDate)),
                HasJustification = !string.IsNullOrWhiteSpace(record.GetAttributeValue<string>(ProjectRequest.Justification)),
                HasCustomerAccount = account != null,
                OtherOpenRequests = account == null ? 0 : CountOtherOpen(service, account.Id, target.Id),
            };

            var result = ProjectRisk.Assess(input, _utcNow());
            local.Tracing.Trace($"{target.Id}: score {result.Score} ({result.Level}): {result.ReasonsText}");

            ctx.OutputParameters["RiskScore"] = result.Score;
            ctx.OutputParameters["RiskLevel"] = result.Level;
            ctx.OutputParameters["Reasons"] = result.ReasonsText;
        }

        /// <summary>Active requests of the same account, this one excluded. Capped: we only need "2 or more".</summary>
        internal static int CountOtherOpen(IOrganizationService service, Guid accountId, Guid self)
        {
            var query = new QueryExpression(ProjectRequest.Table)
            {
                ColumnSet = new ColumnSet(ProjectRequest.Id),
                TopCount = MaxOthersCounted,
            };
            query.Criteria.AddCondition(ProjectRequest.Account, ConditionOperator.Equal, accountId);
            query.Criteria.AddCondition(ProjectRequest.StateCode, ConditionOperator.Equal, 0);
            query.Criteria.AddCondition(ProjectRequest.Id, ConditionOperator.NotEqual, self);
            return service.RetrieveMultiple(query).Entities.Count;
        }
    }
}
