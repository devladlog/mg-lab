using Microsoft.Crm.Sdk.Messages;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Messages;
using Microsoft.Xrm.Sdk.Metadata;
using Xunit;

namespace EquipmentSync.Tests;

public class TableSetupTests
{
    private readonly FakeDataverse dv = new();
    private readonly StringWriter log = new();
    private readonly List<TimeSpan> waits = new();

    private TableSetup Setup(int maxPolls = 60) =>
        new(dv, log, (t, _) => { waits.Add(t); return Task.CompletedTask; }) { MaxPolls = maxPolls };

    [Fact]
    public async Task Creates_the_key_and_waits_for_the_index_to_be_Active()
    {
        dv.PollsUntilActive = 3;
        await Setup().EnsureAlternateKeyAsync();

        var create = dv.Requests.OfType<CreateEntityKeyRequest>().Single();
        Assert.Equal(Equipment.Table, create.EntityName);
        Assert.Equal(new[] { Equipment.AssetTag }, create.EntityKey.KeyAttributes);
        Assert.Equal(EntityKeyIndexStatus.Active, dv.Keys.Single().EntityKeyIndexStatus);
        Assert.Equal(2, waits.Count); // InProgress, InProgress, Active
        Assert.All(waits, w => Assert.Equal(TimeSpan.FromSeconds(5), w));
        Assert.Contains("Alternate key index is Active.", log.ToString());
    }

    [Fact]
    public async Task Re_running_with_an_active_key_changes_nothing()
    {
        dv.ActivateKeyNow();
        await Setup().EnsureAlternateKeyAsync();
        Assert.Empty(dv.Requests.OfType<CreateEntityKeyRequest>());
        Assert.Empty(dv.Requests.OfType<RetrieveEntityKeyRequest>());
    }

    [Fact]
    public async Task A_failed_index_explains_what_to_do()
    {
        dv.KeyIndexFails = true;
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => Setup().EnsureAlternateKeyAsync());
        Assert.Contains("duplicate asset tags", ex.Message);
        Assert.Contains("ReactivateEntityKeyRequest", ex.Message);
    }

    [Fact]
    public async Task Gives_up_after_the_maximum_number_of_checks()
    {
        dv.PollsUntilActive = 100;
        await Assert.ThrowsAsync<TimeoutException>(() => Setup(maxPolls: 3).EnsureAlternateKeyAsync());
        Assert.Equal(3, waits.Count);
    }

    [Fact]
    public async Task Change_tracking_needs_an_explicit_opt_in_because_it_cant_be_undone()
    {
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => Setup().EnsureChangeTrackingAsync(allowEnable: false));
        Assert.Contains("--enable-change-tracking", ex.Message);
        Assert.Empty(dv.Requests.OfType<UpdateEntityRequest>());
        Assert.False(dv.ChangeTrackingEnabled);
    }

    [Fact]
    public async Task Change_tracking_is_enabled_and_published_when_confirmed()
    {
        await Setup().EnsureChangeTrackingAsync(allowEnable: true);
        Assert.True(dv.ChangeTrackingEnabled);
        Assert.True(dv.Requests.OfType<UpdateEntityRequest>().Single().Entity.ChangeTrackingEnabled);
        Assert.Contains("<entity>contoso_equipment</entity>", dv.Requests.OfType<PublishXmlRequest>().Single().ParameterXml);
    }

    [Fact]
    public async Task Change_tracking_already_on_sends_nothing()
    {
        dv.ChangeTrackingEnabled = true;
        await Setup().EnsureChangeTrackingAsync(allowEnable: false);
        Assert.Single(dv.Requests); // only the RetrieveEntity check
    }
}
