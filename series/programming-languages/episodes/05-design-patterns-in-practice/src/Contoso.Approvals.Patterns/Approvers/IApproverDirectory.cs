namespace Contoso.Approvals.Patterns.Approvers;

/// <summary>Who approves for a department and role. The real source is slow (a file read per lookup).</summary>
public interface IApproverDirectory
{
    Task<string> FindAsync(string department, ApproverRole role, CancellationToken cancellationToken = default);
}

/// <summary>Keys for the decorator chain. Only the outermost decorator is registered without a key.</summary>
public static class DirectoryKeys
{
    public const string Source = "directory:source";
    public const string Cached = "directory:cached";
}

/// <summary>Shared counters so the demo (and the tests) can see what each layer did.</summary>
public sealed class DirectoryStats
{
    private int _lookups;
    private int _fileReads;

    public int Lookups => Volatile.Read(ref _lookups);

    public int FileReads => Volatile.Read(ref _fileReads);

    public int ServedFromCache => Lookups - FileReads;

    internal void CountLookup() => Interlocked.Increment(ref _lookups);

    internal void CountFileRead() => Interlocked.Increment(ref _fileReads);
}
