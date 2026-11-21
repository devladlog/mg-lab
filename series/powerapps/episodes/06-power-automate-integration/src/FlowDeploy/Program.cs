using System.Net.Http.Headers;
using FlowDeploy;

// FlowDeploy: create or update the SendLoanReminder cloud flow in a solution from its clientdata file.
//   dotnet run -- <clientdata.json> [--name SendLoanReminder] [--solution EquipmentDesk] [--activate] [--dry-run]
// Needs DATAVERSE_URL (https://<org>.crm4.dynamics.com) and DATAVERSE_TOKEN (a bearer token for that URL), except --dry-run.
// Exit codes: 0 done, 1 error, 2 created/updated but not turned on (a connection reference has no connection yet).

return await Cli.RunAsync(args, Console.Out, Console.Error, Environment.GetEnvironmentVariable, handler: null);

public static class Cli
{
    public static async Task<int> RunAsync(string[] args, TextWriter output, TextWriter error, Func<string, string?> env, HttpMessageHandler? handler)
    {
        if (args.Length == 0 || args[0].StartsWith("--"))
        {
            error.WriteLine("usage: FlowDeploy <clientdata.json> [--name SendLoanReminder] [--solution EquipmentDesk] [--activate] [--dry-run]");
            return 1;
        }
        string Option(string name, string fallback)
        {
            var i = Array.IndexOf(args, name);
            return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback;
        }
        var options = new DeployOptions(
            ClientDataPath: args[0],
            Name: Option("--name", "SendLoanReminder"),
            Solution: Option("--solution", "EquipmentDesk"),
            Activate: args.Contains("--activate"),
            DryRun: args.Contains("--dry-run"),
            Description: "Equipment Desk: sends an overdue-loan reminder when the phone app asks (episode 6).");

        try
        {
            if (options.DryRun) return await new FlowDeployer(new HttpClient(), output).DeployAsync(options);

            var url = env("DATAVERSE_URL") ?? throw new InvalidOperationException("Set DATAVERSE_URL, e.g. https://<org>.crm4.dynamics.com");
            var token = env("DATAVERSE_TOKEN") ?? throw new InvalidOperationException("Set DATAVERSE_TOKEN to a bearer token for " + url);
            using var http = handler is null ? new HttpClient() : new HttpClient(handler, disposeHandler: false);
            http.BaseAddress = new Uri(url.TrimEnd('/') + "/api/data/v9.2/");
            http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
            return await new FlowDeployer(http, output).DeployAsync(options);
        }
        catch (Exception e) when (e is DataverseException or InvalidOperationException or InvalidDataException or FileNotFoundException or HttpRequestException)
        {
            error.WriteLine("error: " + e.Message);
            return 1;
        }
    }
}
