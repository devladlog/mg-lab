using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;
using Moq;
using Xunit;

namespace MGLab.D365.Plugins.Tests;

public class AssessProjectRequestApiTests
{
    private static readonly Guid RecordId = new("00000000-0000-0000-0000-00000000a004");   // PR-0004
    private static readonly Guid AccountId = new("00000000-0000-0000-0000-0000000ac001");
    private static readonly DateTime Now = new(2027, 1, 15, 10, 0, 0, DateTimeKind.Utc);

    private static PluginHarness Harness(int stage = 30, string message = AssessProjectRequestApi.MessageName)
    {
        var h = new PluginHarness(message, ProjectRequest.Table, stage, 0, RecordId);
        h.Inputs["Target"] = new EntityReference(ProjectRequest.Table, RecordId);
        return h;
    }

    private static Entity Record(decimal budget, DateTime? due, string justification, bool withAccount)
    {
        var e = new Entity(ProjectRequest.Table, RecordId) { [ProjectRequest.Budget] = new Money(budget) };
        if (due.HasValue) e[ProjectRequest.DueDate] = due.Value;
        if (justification != null) e[ProjectRequest.Justification] = justification;
        if (withAccount) e[ProjectRequest.Account] = new EntityReference("account", AccountId);
        return e;
    }

    [Fact]
    public void Returns_score_level_and_reasons_as_output_parameters()
    {
        var h = Harness();
        h.Service.Setup(s => s.Retrieve(ProjectRequest.Table, RecordId, It.IsAny<ColumnSet>()))
                 .Returns(Record(75000m, Now.Date.AddDays(10), null, true));
        QueryExpression sent = null;
        h.Service.Setup(s => s.RetrieveMultiple(It.IsAny<QueryBase>()))
                 .Callback<QueryBase>(q => sent = (QueryExpression)q)
                 .Returns(new EntityCollection(new List<Entity> { new(ProjectRequest.Table), new(ProjectRequest.Table) }));

        h.Run(new AssessProjectRequestApi(() => Now));

        Assert.Equal(90, h.Outputs["RiskScore"]);        // 30 budget + 25 no justification + 20 due soon + 15 crowded
        Assert.Equal("High", h.Outputs["RiskLevel"]);
        Assert.Equal("Budget 75,000 is at or over 50,000; No business justification for a large budget; " +
                     "Due in 10 day(s); Account has 2 other open requests", h.Outputs["Reasons"]);

        // the "other open requests" query: same account, active, not this record, capped
        Assert.Equal(AssessProjectRequestApi.MaxOthersCounted, sent.TopCount);
        var c = sent.Criteria.Conditions.Select(x => (x.AttributeName, x.Operator, x.Values[0])).ToList();
        Assert.Contains((ProjectRequest.Account, ConditionOperator.Equal, (object)AccountId), c);
        Assert.Contains((ProjectRequest.StateCode, ConditionOperator.Equal, (object)0), c);
        Assert.Contains((ProjectRequest.Id, ConditionOperator.NotEqual, (object)RecordId), c);
    }

    [Fact]
    public void Retrieves_only_the_columns_the_rules_use()
    {
        var h = Harness();
        ColumnSet cols = null;
        h.Service.Setup(s => s.Retrieve(ProjectRequest.Table, RecordId, It.IsAny<ColumnSet>()))
                 .Callback<string, Guid, ColumnSet>((_, _, c) => cols = c)
                 .Returns(Record(10000m, Now.Date.AddDays(60), null, false));
        h.Run(new AssessProjectRequestApi(() => Now));
        Assert.False(cols.AllColumns);
        Assert.Equal(new[] { ProjectRequest.Budget, ProjectRequest.DueDate, ProjectRequest.Justification, ProjectRequest.Account },
                     cols.Columns);
        h.Service.Verify(s => s.RetrieveMultiple(It.IsAny<QueryBase>()), Times.Never);   // no account: no query
        Assert.Equal("No customer account", h.Outputs["Reasons"]);
    }

    [Fact]
    public void Wrong_target_table_is_a_clear_error()
    {
        var h = Harness();
        h.Inputs["Target"] = new EntityReference("account", AccountId);
        var ex = Assert.Throws<InvalidPluginExecutionException>(() => h.Run(new AssessProjectRequestApi(() => Now)));
        Assert.Contains("needs a mgl_projectrequest as Target", ex.Message);
    }

    [Fact]
    public void Does_nothing_when_registered_on_another_stage()
    {
        var h = Harness(stage: 40);
        h.Run(new AssessProjectRequestApi(() => Now));
        Assert.Empty(h.Outputs);
        Assert.Contains(h.Traces, t => t.Contains("Not registered as the main operation"));
    }

    [Fact]
    public void Unexpected_errors_are_wrapped_and_traced()
    {
        var h = Harness();
        h.Service.Setup(s => s.Retrieve(It.IsAny<string>(), It.IsAny<Guid>(), It.IsAny<ColumnSet>()))
                 .Throws(new TimeoutException("SQL timeout"));
        var ex = Assert.Throws<InvalidPluginExecutionException>(() => h.Run(new AssessProjectRequestApi(() => Now)));
        Assert.Equal("AssessProjectRequestApi failed. See the plug-in trace log.", ex.Message);
        Assert.Contains(h.Traces, t => t.Contains("SQL timeout"));
    }
}
