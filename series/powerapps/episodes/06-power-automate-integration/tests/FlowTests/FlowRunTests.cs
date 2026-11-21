using FlowTests.Wdl;
using Xunit;

namespace FlowTests;

/// <summary>The flow definition from src/flow, run path by path against the fake connectors. Today is Mon 30 Nov 2026.</summary>
public class FlowRunTests
{
    [Fact]
    public void An_overdue_loan_gets_an_email_and_the_app_gets_sent_true()
    {
        var fakes = new FakeConnectors();
        var run = Flow.Run(fakes, FakeConnectors.OverdueLoan);

        var mail = Assert.Single(fakes.SentMail);
        Assert.Equal("alex.demo@contoso.com", (string)mail["emailMessage/To"]!);
        Assert.Equal("Please return CT-0043 Laptop 14", (string)mail["emailMessage/Subject"]!);
        Assert.Contains("was due back on Monday 16 November 2026.", (string)mail["emailMessage/Body"]!);
        Assert.Equal("Respond_sent", run.Response!.Action);
        Assert.True((bool)run.Response.Body["sent"]!);
        Assert.Equal("Reminder sent to alex.demo@contoso.com for CT-0043.", (string)run.Response.Body["message"]!);
    }

    [Fact]
    public void The_flow_reads_the_loan_itself_with_the_id_from_the_app()
    {
        var fakes = new FakeConnectors();
        var run = Flow.Run(fakes, FakeConnectors.OverdueLoan);

        var get = run.Calls.First();
        Assert.Equal(("shared_commondataserviceforapps", "GetItem"), (get.Connection, get.OperationId));
        Assert.Equal("contoso_loans", (string)get.Parameters["entityName"]!);
        Assert.Equal(FakeConnectors.OverdueLoan.ToString(), (string)get.Parameters["recordId"]!);
        Assert.Equal("contoso_name,contoso_borroweremail,contoso_duedate,contoso_returnedon", (string)get.Parameters["$select"]!);
        Assert.Equal("contoso_EquipmentId($select=contoso_assettag,contoso_name)", (string)get.Parameters["$expand"]!);
    }

    [Theory]
    [InlineData("00000000-0000-0000-0000-000000000042", "No reminder sent: it was already returned.")]
    [InlineData("00000000-0000-0000-0000-000000000108", "No reminder sent: it isn't overdue yet.")]           // due today
    [InlineData("00000000-0000-0000-0000-000000000311", "No reminder sent: the borrower isn't a contoso.com address.")]
    public void Loans_that_must_not_be_reminded_get_a_reason_and_no_email(string loanId, string message)
    {
        var fakes = new FakeConnectors();
        var run = Flow.Run(fakes, loanId);

        Assert.Empty(fakes.SentMail);
        Assert.Equal("Respond_skipped", run.Response!.Action);
        Assert.False((bool)run.Response.Body["sent"]!);
        Assert.Equal(message, (string)run.Response.Body["message"]!);
        Assert.Equal("Skipped", run.Status["Send_reminder"]);
    }

    [Fact]
    public void The_domain_check_ignores_case_because_endsWith_does()
    {
        var fakes = new FakeConnectors();
        var run = Flow.Run(fakes, FakeConnectors.UpperCaseLoan);

        Assert.True((bool)run.Response!.Body["sent"]!); // Learn: endsWith "isn't case-sensitive"
        Assert.Equal("Jordan.Demo@CONTOSO.COM", (string)Assert.Single(fakes.SentMail)["emailMessage/To"]!);
    }

    [Theory]
    [InlineData("00000000-0000-0000-0000-000000000999")]   // exists, but the invoking user can't read it
    [InlineData("00000000-0000-0000-0000-000000000001")]   // doesn't exist
    [InlineData("not-a-guid")]                             // a tampered call
    public void A_loan_the_user_cannot_read_is_a_polite_no_not_a_failed_run(string loanId)
    {
        var fakes = new FakeConnectors();
        var run = Flow.Run(fakes, loanId);

        Assert.Equal("Failed", run.Status["Get_loan"]);
        Assert.Equal("Respond_not_found", run.Response!.Action);
        Assert.False((bool)run.Response.Body["sent"]!);
        Assert.Empty(fakes.SentMail);
        Assert.Equal("Skipped", run.Status["Problem"]);
    }

    [Fact]
    public void A_Dataverse_timeout_still_answers_the_app()
    {
        var run = Flow.Run(new FakeConnectors { DataverseTimesOut = true }, FakeConnectors.OverdueLoan);
        Assert.Equal("Respond_not_found", run.Response!.Action);
    }

    [Fact]
    public void When_Outlook_fails_the_app_hears_why()
    {
        var fakes = new FakeConnectors
        {
            MailResult = new ConnectorResult(400, Newtonsoft.Json.Linq.JObject.Parse("""{"error":{"message":"Mailbox is not enabled"}}""")),
        };
        var run = Flow.Run(fakes, FakeConnectors.OverdueLoan);

        Assert.Equal("Failed", run.Status["Send_reminder"]);
        Assert.Equal("Respond_send_failed", run.Response!.Action);
        Assert.Equal("The reminder couldn't be sent: Mailbox is not enabled", (string)run.Response.Body["message"]!);
        Assert.Equal("Skipped", run.Status["Respond_sent"]);
    }

    [Fact]
    public void Overdue_means_overdue_in_Lisbon_not_in_UTC()
    {
        // 14 Jul 2026 23:30 UTC is already 15 Jul 00:30 in Lisbon (summer time, UTC+1): a loan due on the 14th is overdue.
        var lateEvening = new DateTimeOffset(2026, 7, 14, 23, 30, 0, TimeSpan.Zero);
        var run = Flow.Run(new FakeConnectors(), FakeConnectors.SummerLoan, lateEvening);
        Assert.True((bool)run.Response!.Body["sent"]!);

        // An hour earlier (22:30 UTC, 23:30 in Lisbon) it's still the 14th: not overdue yet.
        var run2 = Flow.Run(new FakeConnectors(), FakeConnectors.SummerLoan, lateEvening.AddMinutes(-60));
        Assert.Equal("No reminder sent: it isn't overdue yet.", (string)run2.Response!.Body["message"]!);
    }

    public static TheoryData<string, Action<FakeConnectors>> EveryPath => new()
    {
        { "00000000-0000-0000-0000-000000000043", _ => { } },
        { "00000000-0000-0000-0000-000000000042", _ => { } },
        { "00000000-0000-0000-0000-000000000108", _ => { } },
        { "00000000-0000-0000-0000-000000000311", _ => { } },
        { "00000000-0000-0000-0000-000000000999", _ => { } },
        { "00000000-0000-0000-0000-000000000043", f => f.MailResult = new ConnectorResult(500, new Newtonsoft.Json.Linq.JObject()) },
        { "00000000-0000-0000-0000-000000000043", f => f.MailResult = new ConnectorResult(504, new Newtonsoft.Json.Linq.JObject(), TimedOut: true) },
        { "00000000-0000-0000-0000-000000000043", f => f.DataverseTimesOut = true },
    };

    [Theory]
    [MemberData(nameof(EveryPath))]
    public void Every_path_answers_the_app_exactly_once(string loanId, Action<FakeConnectors> setup)
    {
        // A path without a Response leaves the app waiting until the 120-second limit (Learn: ResponseTimeout).
        var fakes = new FakeConnectors();
        setup(fakes);
        var run = Flow.Run(fakes, loanId);

        Assert.Single(run.AllResponses);
        Assert.Equal(200, run.Response!.StatusCode);
    }

    [Fact]
    public void Power_Apps_must_send_the_loan_id()
    {
        var ex = Assert.Throws<ArgumentException>(() =>
            new FlowRunner(Files.Definition(), new FakeConnectors().Handle, Flow.Now).Run(new Newtonsoft.Json.Linq.JObject()));
        Assert.Contains("LoanId", ex.Message);
    }
}
