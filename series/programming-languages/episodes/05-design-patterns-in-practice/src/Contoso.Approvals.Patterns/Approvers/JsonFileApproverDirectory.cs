using System.Text.Json;
using Microsoft.Extensions.Options;

namespace Contoso.Approvals.Patterns.Approvers;

/// <summary>The component being decorated: reads approvers.json on every call, on purpose.</summary>
public sealed class JsonFileApproverDirectory(IOptions<ApproverDirectoryOptions> options, DirectoryStats stats)
    : IApproverDirectory
{
    public async Task<string> FindAsync(string department, ApproverRole role, CancellationToken cancellationToken = default)
    {
        stats.CountFileRead();
        await using var stream = File.OpenRead(options.Value.File);
        var file = await JsonSerializer.DeserializeAsync<ApproversFile>(stream, JsonSerializerOptions.Web, cancellationToken)
            .ConfigureAwait(false)
            ?? throw new InvalidOperationException($"{options.Value.File} is empty.");

        if (role == ApproverRole.Board)
        {
            return file.Board;
        }

        return file.Departments.TryGetValue(department, out var roles) && roles.TryGetValue(role.ToString(), out var name)
            ? name
            : throw new InvalidOperationException($"No {role} approver for department '{department}'.");
    }

    private sealed record ApproversFile(string Board, Dictionary<string, Dictionary<string, string>> Departments);
}
