namespace Demo;

public static class AsyncMistakes
{
    // CS4014: the call is not awaited. The method returns before the file is written,
    // and any exception from WriteAllTextAsync is never observed.
    public static async Task SaveAuditAsync(string path, string line)
    {
        File.WriteAllTextAsync(path, line);
        await Task.CompletedTask;
    }

    // CA2016: we were given a token but don't pass it on. Ctrl+C would not stop this download.
    public static async Task<string> DownloadAsync(HttpClient http, Uri uri, CancellationToken ct)
    {
        return await http.GetStringAsync(uri);
    }

    // CA1849: blocking inside an async method. This thread waits instead of being returned to the pool.
    public static async Task<int> CountRequestsAsync(Task<int[]> load)
    {
        await Task.Yield();
        return load.Result.Length;
    }
}
