using System.Text.Json;
using Contoso.Approvals.Patterns.Approvers;
using Contoso.Approvals.Patterns.Events;
using Microsoft.Extensions.DependencyInjection;

namespace Contoso.Approvals.Patterns.Tests;

public class EndToEndTests
{
    [Fact]
    public async Task The_sample_batches_route_like_the_video_shows()
    {
        using var sp = TestHost.Provider();
        await using var json = File.OpenRead(TestHost.RequestsFile);
        var batches = await JsonSerializer.DeserializeAsync<ProjectRequest[][]>(json, JsonSerializerOptions.Web);
        var routes = new List<string>();

        foreach (var batch in batches!)
        {
            using var scope = sp.CreateScope();
            var service = scope.ServiceProvider.GetRequiredService<ApprovalService>();
            foreach (var request in batch)
            {
                routes.Add((await service.SubmitAsync(request)).Routed.Route);
            }

            Assert.Equal(batch.Length, scope.ServiceProvider.GetRequiredService<AuditTrail>().Entries.Count);
        }

        Assert.Equal(["standard", "standard", "board", "high", "high", "board", "standard", "high"], routes);
        var stats = sp.GetRequiredService<DirectoryStats>();
        Assert.Equal((13, 10, 3), (stats.Lookups, stats.FileReads, stats.ServedFromCache));
    }
}
