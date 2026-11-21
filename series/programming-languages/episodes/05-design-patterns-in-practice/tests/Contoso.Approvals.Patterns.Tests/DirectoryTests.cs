using Contoso.Approvals.Patterns.Approvers;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.Extensions.Time.Testing;

namespace Contoso.Approvals.Patterns.Tests;

public class DirectoryTests
{
    private static readonly IOptions<ApproverDirectoryOptions> Options =
        Microsoft.Extensions.Options.Options.Create(new ApproverDirectoryOptions { File = TestHost.ApproversFile, CacheSeconds = 300 });

    [Fact]
    public async Task The_file_directory_reads_the_file_on_every_lookup()
    {
        var stats = new DirectoryStats();
        var directory = new JsonFileApproverDirectory(Options, stats);

        Assert.Equal("Alex Demo", await directory.FindAsync("IT", ApproverRole.Manager));
        Assert.Equal("Alex Demo", await directory.FindAsync("IT", ApproverRole.Manager));
        Assert.Equal(2, stats.FileReads);
    }

    [Fact]
    public async Task Board_ignores_the_department_and_unknown_departments_fail_clearly()
    {
        var directory = new JsonFileApproverDirectory(Options, new DirectoryStats());

        Assert.Equal("Taylor Demo", await directory.FindAsync("Legal", ApproverRole.Board));
        var ex = await Assert.ThrowsAsync<InvalidOperationException>(() => directory.FindAsync("Legal", ApproverRole.Manager));
        Assert.Equal("No Manager approver for department 'Legal'.", ex.Message);
    }

    [Fact]
    public async Task The_caching_decorator_serves_repeats_and_expires_with_the_clock()
    {
        var stats = new DirectoryStats();
        var time = new FakeTimeProvider();
        var cached = new CachingApproverDirectory(new JsonFileApproverDirectory(Options, stats), time, Options);

        await cached.FindAsync("IT", ApproverRole.Finance);
        await cached.FindAsync("IT", ApproverRole.Finance);
        Assert.Equal(1, stats.FileReads);

        time.Advance(TimeSpan.FromSeconds(299));
        await cached.FindAsync("IT", ApproverRole.Finance);
        Assert.Equal(1, stats.FileReads);

        time.Advance(TimeSpan.FromSeconds(1));
        await cached.FindAsync("IT", ApproverRole.Finance);
        Assert.Equal(2, stats.FileReads);
    }

    [Fact]
    public async Task Decorator_order_changes_what_you_measure()
    {
        var outside = new DirectoryStats();
        var meteredOutside = new MeteredApproverDirectory(
            new CachingApproverDirectory(new JsonFileApproverDirectory(Options, outside), new FakeTimeProvider(), Options), outside);

        var inside = new DirectoryStats();
        var meteredInside = new CachingApproverDirectory(
            new MeteredApproverDirectory(new JsonFileApproverDirectory(Options, inside), inside), new FakeTimeProvider(), Options);

        for (var i = 0; i < 3; i++)
        {
            await meteredOutside.FindAsync("HR", ApproverRole.Manager);
            await meteredInside.FindAsync("HR", ApproverRole.Manager);
        }

        Assert.Equal(3, outside.Lookups);   // every call
        Assert.Equal(1, inside.Lookups);    // only cache misses
    }

    [Fact]
    public void Only_the_outer_decorator_is_resolvable_without_a_key()
    {
        using var sp = TestHost.Provider();

        Assert.IsType<MeteredApproverDirectory>(sp.GetRequiredService<IApproverDirectory>());
        Assert.Single(sp.GetServices<IApproverDirectory>());
        Assert.IsType<JsonFileApproverDirectory>(sp.GetRequiredKeyedService<IApproverDirectory>(DirectoryKeys.Source));
        Assert.IsType<CachingApproverDirectory>(sp.GetRequiredKeyedService<IApproverDirectory>(DirectoryKeys.Cached));
    }
}
