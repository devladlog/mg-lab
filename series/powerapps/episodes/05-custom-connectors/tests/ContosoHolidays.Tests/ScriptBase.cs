// Supporting classes for custom connector code, as Learn defines them ("Use custom code in a custom connector",
// Definition of supporting classes and interfaces: "Use them for local testing and compilation").
// Written in C# 7.3 so ScriptCompileTests can compile this file together with script.csx for .NET Standard 2.0.
// Only the Initialize method is ours: the platform sets Context and CancellationToken, tests do it here.
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;

public abstract class ScriptBase
{
    // Context object
    public IScriptContext Context { get; private set; }

    // CancellationToken for the execution
    public CancellationToken CancellationToken { get; private set; }

    // Helper: Creates a StringContent object from the serialized JSON
    public static StringContent CreateJsonContent(string serializedJson)
    {
        return new StringContent(serializedJson, Encoding.UTF8, "application/json");
    }

    // Abstract method for your code
    public abstract Task<HttpResponseMessage> ExecuteAsync();

    // Test harness only (not part of the platform's class).
    internal void Initialize(IScriptContext context, CancellationToken cancellationToken)
    {
        this.Context = context;
        this.CancellationToken = cancellationToken;
    }
}

public interface IScriptContext
{
    // Correlation Id
    string CorrelationId { get; }

    // Connector Operation Id
    string OperationId { get; }

    // Incoming request
    HttpRequestMessage Request { get; }

    // Logger instance
    ILogger Logger { get; }

    // Used to send an HTTP request
    // Use this method to send requests instead of HttpClient.SendAsync
    Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken);
}
