using Microsoft.Xrm.Sdk;
using Moq;
using Xunit;

namespace MGLab.D365.Plugins.Tests;

public class RiskScoreRefreshPluginTests
{
    private static readonly Guid RecordId = new("00000000-0000-0000-0000-00000000a004");

    private static PluginHarness Harness(int? scoreInPostImage, int newScore, string message = "Update", int stage = 40, int mode = 1)
    {
        var h = new PluginHarness(message, ProjectRequest.Table, stage, mode, RecordId, depth: 1);
        var post = new Entity(ProjectRequest.Table, RecordId);
        if (scoreInPostImage.HasValue) post[ProjectRequest.RiskScore] = scoreInPostImage.Value;
        h.PostImages[RiskScoreRefreshPlugin.PostImageName] = post;

        var response = new OrganizationResponse();
        response.Results["RiskScore"] = newScore;
        response.Results["RiskLevel"] = ProjectRisk.LevelFor(newScore);
        response.Results["Reasons"] = "test";
        h.Service.Setup(s => s.Execute(It.Is<OrganizationRequest>(r => r.RequestName == AssessProjectRequestApi.MessageName)))
                 .Returns(response);
        return h;
    }

    [Fact]
    public void Calls_the_custom_api_for_this_record_and_writes_only_the_score()
    {
        var h = Harness(scoreInPostImage: 30, newScore: 75);
        Entity updated = null;
        h.Service.Setup(s => s.Update(It.IsAny<Entity>())).Callback<Entity>(e => updated = e);

        h.Run(new RiskScoreRefreshPlugin());

        h.Service.Verify(s => s.Execute(It.Is<OrganizationRequest>(r =>
            ((EntityReference)r["Target"]).Id == RecordId && ((EntityReference)r["Target"]).LogicalName == ProjectRequest.Table)));
        Assert.Equal(RecordId, updated.Id);
        Assert.Equal(new[] { ProjectRequest.RiskScore }, updated.Attributes.Keys);   // nothing else: no loop
        Assert.Equal(75, updated[ProjectRequest.RiskScore]);
        Assert.Contains(h.Traces, t => t.Contains("Risk score 30 -> 75 (High)"));
    }

    [Fact]
    public void Same_score_means_no_update()
    {
        var h = Harness(scoreInPostImage: 75, newScore: 75);
        h.Run(new RiskScoreRefreshPlugin());
        h.Service.Verify(s => s.Update(It.IsAny<Entity>()), Times.Never);
        Assert.Contains(h.Traces, t => t.Contains("unchanged (75)"));
    }

    [Fact]
    public void First_score_on_create_is_written()
    {
        var h = Harness(scoreInPostImage: null, newScore: 0, message: "Create");
        h.Run(new RiskScoreRefreshPlugin());
        h.Service.Verify(s => s.Update(It.Is<Entity>(e => (int)e[ProjectRequest.RiskScore] == 0)), Times.Once);
        Assert.Contains(h.Traces, t => t.Contains("(empty) -> 0"));
    }

    [Theory]
    [InlineData(40, 0)]   // post-operation but synchronous
    [InlineData(20, 1)]   // not post-operation
    public void Wrong_registration_is_traced_and_ignored(int stage, int mode)
    {
        var h = Harness(30, 75, stage: stage, mode: mode);
        h.Run(new RiskScoreRefreshPlugin());
        h.Service.Verify(s => s.Execute(It.IsAny<OrganizationRequest>()), Times.Never);
        Assert.Contains(h.Traces, t => t.Contains("expected post-operation, asynchronous"));
    }
}
