using System.Globalization;
using Grpc.Core;
using ProjectRequests.Grpc;

namespace ProjectRequests.Cli;

/// <summary>The three call shapes against the same service. Output goes to a TextWriter so tests can read it.</summary>
public static class Commands
{
    /// <summary>Unary: one message out, one message back. A status other than OK becomes an RpcException.</summary>
    public static async Task GetAsync(Requests.RequestsClient client, int id, TimeSpan timeout, TextWriter output, CancellationToken ct)
    {
        var reply = await client.GetRequestAsync(
            new GetRequestMessage { Id = id },
            deadline: DateTime.UtcNow.Add(timeout),                  // a deadline is UTC; there is no default one
            cancellationToken: ct);
        output.WriteLine(Describe(reply));
        if (reply.Justification is { Length: > 0 } text)
            output.WriteLine($"   justification: {text}");
    }

    /// <summary>Server streaming: each row is printed the moment it arrives, not after the last one.</summary>
    public static async Task<int> ListAsync(Requests.RequestsClient client, string? department, TimeSpan timeout, TextWriter output, CancellationToken ct)
    {
        using var call = client.ListRequests(
            new ListRequestsMessage { Department = department ?? "" },
            deadline: DateTime.UtcNow.Add(timeout),
            cancellationToken: ct);

        var count = 0;
        await foreach (var reply in call.ResponseStream.ReadAllAsync(ct))
        {
            output.WriteLine(Describe(reply));
            count++;
        }
        output.WriteLine($"{count} request(s)");
        return count;
    }

    /// <summary>
    /// Client streaming: rows are written to the open request stream one by one, CompleteAsync says "no more",
    /// and the single reply arrives last. Lines the CSV reader rejects never leave the client.
    /// </summary>
    public static async Task<ImportOutcome> ImportAsync(Requests.RequestsClient client, IEnumerable<CsvRow> rows, TimeSpan timeout, TextWriter output, CancellationToken ct)
    {
        var sentLines = new List<int>();                             // stream position -> line in the file
        var localErrors = 0;

        using var call = client.ImportRequests(deadline: DateTime.UtcNow.Add(timeout), cancellationToken: ct);
        foreach (var row in rows)
        {
            if (row.Message is null)
            {
                output.WriteLine($"line {row.Line}: skipped, {row.Error}");
                localErrors++;
                continue;
            }
            await call.RequestStream.WriteAsync(row.Message, ct);
            sentLines.Add(row.Line);
        }
        await call.RequestStream.CompleteAsync();

        var reply = await call.ResponseAsync;
        output.WriteLine($"server received {reply.Received} row(s), created {reply.CreatedIds.Count}: [{string.Join(", ", reply.CreatedIds)}]");
        foreach (var error in reply.Errors)
        {
            var line = error.Row >= 1 && error.Row <= sentLines.Count ? sentLines[error.Row - 1] : error.Row;
            output.WriteLine($"line {line}: {error.Field}: {error.Message}");
        }
        return new ImportOutcome(reply.Received, reply.CreatedIds.Count, reply.Errors.Count + localErrors);
    }

    public static string Describe(RequestReply r) => string.Create(CultureInfo.InvariantCulture,
        $"#{r.Id} {r.Department,-3} {r.Title,-28} {(decimal)r.Budget,12:N0}  {r.Priority,-8} {r.Status}{(r.DecidedBy is null ? "" : " by " + r.DecidedBy)}");
}

public sealed record ImportOutcome(int Received, int Created, int Errors);
