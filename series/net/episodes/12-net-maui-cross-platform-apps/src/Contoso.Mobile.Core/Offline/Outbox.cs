using System.Text.Json;
using Contoso.Mobile.Core.Models;

namespace Contoso.Mobile.Core.Offline;

/// <summary>Drafts waiting to be sent. Survives the app being closed.</summary>
public interface IOutbox
{
    Task<IReadOnlyList<DraftRequest>> ListAsync(CancellationToken ct = default);
    Task AddAsync(DraftRequest draft, CancellationToken ct = default);
    Task RemoveAsync(Guid key, CancellationToken ct = default);
    Task MarkRejectedAsync(Guid key, string error, CancellationToken ct = default);
}

/// <summary>The last list the server gave us, so the app has something to show with no network.</summary>
public interface IRequestCache
{
    Task<IReadOnlyList<RequestItem>> LoadAsync(CancellationToken ct = default);
    Task SaveAsync(IReadOnlyList<RequestItem> items, CancellationToken ct = default);
}

/// <summary>
/// One small JSON file per store, in the app's data folder (on a device: <c>FileSystem.AppDataDirectory</c>).
/// Written to a temp file and moved over the old one, so a crash mid-write can't leave half a file.
/// A file instead of SQLite on purpose: no native library to ship for Android, iOS and Windows for what is a short queue.
/// </summary>
public sealed class JsonFileStore<T>(string path) where T : class
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web) { WriteIndented = true };

    public async Task<TResult> UpdateAsync<TResult>(Func<List<T>, TResult> change, CancellationToken ct, bool save = true)
    {
        await _gate.WaitAsync(ct);
        try
        {
            var items = await ReadAsync(ct);
            var result = change(items);
            if (save) await WriteAsync(items, ct);
            return result;
        }
        finally { _gate.Release(); }
    }

    private async Task<List<T>> ReadAsync(CancellationToken ct)
    {
        if (!File.Exists(path)) return [];
        try
        {
            await using var stream = File.OpenRead(path);
            return await JsonSerializer.DeserializeAsync<List<T>>(stream, Options, ct) ?? [];
        }
        catch (JsonException)
        {
            // A damaged file must not brick the app: set it aside (so nothing is silently destroyed) and start empty.
            File.Move(path, $"{path}.damaged-{DateTime.UtcNow:yyyyMMddHHmmss}", overwrite: true);
            return [];
        }
    }

    private async Task WriteAsync(List<T> items, CancellationToken ct)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        var temp = path + ".tmp";
        await using (var stream = File.Create(temp))
            await JsonSerializer.SerializeAsync(stream, items, Options, ct);
        File.Move(temp, path, overwrite: true);
    }
}

public sealed class FileOutbox(string path) : IOutbox
{
    private readonly JsonFileStore<DraftRequest> _store = new(path);

    public Task<IReadOnlyList<DraftRequest>> ListAsync(CancellationToken ct = default) =>
        _store.UpdateAsync(items => (IReadOnlyList<DraftRequest>)items.OrderBy(d => d.QueuedAtUtc).ToList(), ct, save: false);

    public Task AddAsync(DraftRequest draft, CancellationToken ct = default) =>
        _store.UpdateAsync(items => { if (items.All(d => d.Key != draft.Key)) items.Add(draft); return 0; }, ct);

    public Task RemoveAsync(Guid key, CancellationToken ct = default) =>
        _store.UpdateAsync(items => items.RemoveAll(d => d.Key == key), ct);

    public Task MarkRejectedAsync(Guid key, string error, CancellationToken ct = default) =>
        _store.UpdateAsync(items =>
        {
            var i = items.FindIndex(d => d.Key == key);
            if (i >= 0) items[i] = items[i] with { Error = error };
            return 0;
        }, ct);
}

public sealed class FileRequestCache(string path) : IRequestCache
{
    private readonly JsonFileStore<RequestItem> _store = new(path);

    public async Task<IReadOnlyList<RequestItem>> LoadAsync(CancellationToken ct = default) =>
        await _store.UpdateAsync(items => (IReadOnlyList<RequestItem>)items.ToList(), ct, save: false);

    public Task SaveAsync(IReadOnlyList<RequestItem> items, CancellationToken ct = default) =>
        _store.UpdateAsync(list => { list.Clear(); list.AddRange(items); return 0; }, ct);
}
