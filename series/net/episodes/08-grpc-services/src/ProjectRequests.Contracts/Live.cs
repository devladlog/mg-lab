namespace ProjectRequests.Contracts;

/// <summary>
/// Episode 7: the methods the SERVER calls on connected clients. The hub is a Hub&lt;IRequestsClient&gt;, so a typo
/// is a compile error on the server; the clients register handlers with nameof(...) on the same names.
/// No ASP.NET Core dependency: this file also runs in the browser (WebAssembly).
/// </summary>
public interface IRequestsClient
{
    /// <summary>A new request was submitted.</summary>
    Task RequestCreated(RequestDto request);

    /// <summary>An existing request changed: budget updated, approved or rejected.</summary>
    Task RequestUpdated(RequestDto request);
}

/// <summary>The hub's address and the methods clients may call on it.</summary>
public static class RequestsHubContract
{
    /// <summary>Relative to the API's base address.</summary>
    public const string Path = "hubs/requests";

    /// <summary>
    /// Watch(string? department): null = every department, otherwise one department code.
    /// Returns the group the connection is now in. Group membership lives on the server, per connection.
    /// </summary>
    public const string Watch = "Watch";
}
