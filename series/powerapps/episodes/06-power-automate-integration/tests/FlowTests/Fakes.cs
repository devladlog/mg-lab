using FlowTests.Wdl;
using Newtonsoft.Json.Linq;

namespace FlowTests;

public static class Files
{
    public static string EpisodeDir { get; } = FindEpisodeDir();
    public static string ClientDataPath => Path.Combine(EpisodeDir, "src", "flow", "SendLoanReminder.clientdata.json");
    public static JObject ClientData() => JObject.Parse(File.ReadAllText(ClientDataPath));
    public static JObject Definition() => (JObject)ClientData()["properties"]!["definition"]!;
    public static string LoansScreen => Path.Combine(EpisodeDir, "src", "app", "Src", "LoansScreen.pa.yaml");

    private static string FindEpisodeDir()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !Directory.Exists(Path.Combine(dir.FullName, "src", "flow"))) dir = dir.Parent;
        return dir?.FullName ?? throw new DirectoryNotFoundException("episode folder");
    }
}

/// <summary>
/// Stand-ins for the two connectors, shaped like their documented operations: Dataverse "Get a row by ID" (GetItem:
/// entityName, recordId, $select, $expand) and Office 365 Outlook "Send an email (V2)" (SendEmailV2: To, Subject, Body).
/// Loans look like episode 1's contoso_loan rows with the Equipment lookup expanded.
/// </summary>
public sealed class FakeConnectors
{
    public static readonly Guid OverdueLoan = new("00000000-0000-0000-0000-000000000043");
    public static readonly Guid ReturnedLoan = new("00000000-0000-0000-0000-000000000042");
    public static readonly Guid NotDueLoan = new("00000000-0000-0000-0000-000000000108");
    public static readonly Guid ExternalLoan = new("00000000-0000-0000-0000-000000000311");
    public static readonly Guid UpperCaseLoan = new("00000000-0000-0000-0000-000000000107");
    public static readonly Guid SummerLoan = new("00000000-0000-0000-0000-000000000500");
    public static readonly Guid SecretLoan = new("00000000-0000-0000-0000-000000000999");

    public Dictionary<Guid, JObject> Loans { get; } = new()
    {
        [OverdueLoan] = Loan("CT-0043", "Laptop 14", "alex.demo@contoso.com", "2026-11-16", null),
        [ReturnedLoan] = Loan("CT-0042", "Laptop 14", "jordan.demo@contoso.com", "2026-11-16", "2026-11-20"),
        [NotDueLoan] = Loan("CT-0108", "Monitor 24", "sam.demo@contoso.com", "2026-11-30", null),       // due today
        [ExternalLoan] = Loan("CT-0311", "Phone", "alex.demo@fabrikam.com", "2026-11-02", null),
        [UpperCaseLoan] = Loan("CT-0107", "Monitor 27", "Jordan.Demo@CONTOSO.COM", "2026-11-27", null),
        [SummerLoan] = Loan("CT-0500", "Projector", "sam.demo@contoso.com", "2026-07-14", null),
        [SecretLoan] = Loan("CT-0999", "Prototype", "alex.demo@contoso.com", "2026-11-01", null),
    };

    /// <summary>Rows the invoking user can't read (Dataverse security): GetItem fails like a privilege error.</summary>
    public HashSet<Guid> NotReadable { get; } = new() { SecretLoan };

    public ConnectorResult? MailResult { get; set; }
    public bool DataverseTimesOut { get; set; }
    public List<JObject> SentMail { get; } = new();

    public ConnectorResult Handle(ConnectorCall call) => (call.Connection, call.OperationId) switch
    {
        ("shared_commondataserviceforapps", "GetItem") => GetItem(call.Parameters),
        ("shared_office365", "SendEmailV2") => SendMail(call.Parameters),
        _ => throw new NotSupportedException($"{call.Connection}/{call.OperationId}"),
    };

    private ConnectorResult GetItem(JObject p)
    {
        if (DataverseTimesOut) return new ConnectorResult(504, new JObject(), TimedOut: true);
        if ((string)p["entityName"]! != "contoso_loans") return new ConnectorResult(404, Error("Entity set not found"));
        if (!Guid.TryParse((string)p["recordId"]!, out var id)) return new ConnectorResult(400, Error("Invalid row id"));
        if (!Loans.TryGetValue(id, out var row)) return new ConnectorResult(404, Error("contoso_loan With Id = " + id + " Does Not Exist"));
        if (NotReadable.Contains(id)) return new ConnectorResult(403, Error("Principal user is missing prvReadcontoso_loan privilege"));

        var result = new JObject { ["contoso_loanid"] = id.ToString() };
        foreach (var column in ((string)p["$select"]!).Split(',')) result[column] = row[column]?.DeepClone() ?? JValue.CreateNull();
        if (((string?)p["$expand"])?.StartsWith("contoso_EquipmentId(") == true) result["contoso_EquipmentId"] = row["contoso_EquipmentId"]!.DeepClone();
        return ConnectorResult.Ok(result);
    }

    private ConnectorResult SendMail(JObject p)
    {
        if (MailResult != null) return MailResult;
        SentMail.Add(p);
        return new ConnectorResult(200, new JObject());
    }

    private static JObject Error(string message) => new() { ["error"] = new JObject { ["message"] = message } };

    private static JObject Loan(string tag, string device, string email, string due, string? returned) => new()
    {
        ["contoso_name"] = $"{tag} - {email.Split('@')[0]}",
        ["contoso_borroweremail"] = email,
        ["contoso_duedate"] = due,                     // DateOnly columns come back as yyyy-MM-dd
        ["contoso_returnedon"] = returned is null ? JValue.CreateNull() : returned,
        ["contoso_EquipmentId"] = new JObject { ["contoso_assettag"] = tag, ["contoso_name"] = device },
    };
}

public static class Flow
{
    /// <summary>Mon 30 Nov 2026, 10:00 UTC (= 10:00 in Lisbon in winter).</summary>
    public static readonly DateTimeOffset Now = new(2026, 11, 30, 10, 0, 0, TimeSpan.Zero);

    public static FlowRun Run(FakeConnectors fakes, Guid loanId, DateTimeOffset? now = null) =>
        Run(fakes, loanId.ToString(), now);

    public static FlowRun Run(FakeConnectors fakes, string loanId, DateTimeOffset? now = null) =>
        new FlowRunner(Files.Definition(), fakes.Handle, now ?? Now).Run(new JObject { ["text"] = loanId });
}
