using Contoso.InvoiceApproval;
using Microsoft.DurableTask.Client;

namespace InvoiceApproval.Tests;

public class OrchestrationTests
{
    [Fact]
    public async Task Small_invoice_needs_only_the_manager()
    {
        await using var w = await TestWorld.StartAsync();
        var id = await w.StartApprovalAsync(TestWorld.Invoice(total: 1476m), TestWorld.Settings());

        var request = await w.WaitForRequestAsync(1);
        Assert.Equal((People.Sam, "Manager", ApprovalStatus.Waiting), (request.ApproverEmail, request.Stage, request.Status));
        Assert.StartsWith($"{TestWorld.BaseUrl}api/approvals/invoice-fabrikam-INV1001/", request.CallbackUrl);

        Assert.Equal(202, (await w.AnswerAsync(request, "Approve", People.Sam, "OK to pay")).StatusCode);

        var outcome = await w.WaitForOutcomeAsync(id);
        Assert.Equal(ApprovalStatus.Approved, outcome.Status);
        Assert.Single(outcome.Stages);
        var recorded = Assert.Single(w.Flow.Outcomes);
        Assert.Equal((ApprovalStatus.Approved, People.Sam, 7), (recorded.Status, recorded.DecidedBy, recorded.ItemId));
    }

    [Fact]
    public async Task Above_the_threshold_the_finance_director_approves_after_the_manager()
    {
        await using var w = await TestWorld.StartAsync();
        var id = await w.StartApprovalAsync(TestWorld.Invoice(total: 7380m), TestWorld.Settings());

        await w.AnswerAsync(await w.WaitForRequestAsync(1), "Approve", People.Sam);
        var finance = await w.WaitForRequestAsync(2);
        Assert.Equal((People.Jordan, "Finance"), (finance.ApproverEmail, finance.Stage));
        await w.AnswerAsync(finance, "Approve", People.Jordan);

        var outcome = await w.WaitForOutcomeAsync(id);
        Assert.Equal(ApprovalStatus.Approved, outcome.Status);
        Assert.Equal("Manager: Approved by sam.demo@contoso.com; Finance: Approved by jordan.demo@contoso.com", outcome.Summary);
    }

    [Fact]
    public async Task A_rejection_ends_the_workflow_and_finance_is_never_asked()
    {
        await using var w = await TestWorld.StartAsync();
        var id = await w.StartApprovalAsync(TestWorld.Invoice(total: 7380m), TestWorld.Settings());

        await w.AnswerAsync(await w.WaitForRequestAsync(1), "Reject", People.Sam, "Wrong cost center");

        var outcome = await w.WaitForOutcomeAsync(id);
        Assert.Equal(ApprovalStatus.Rejected, outcome.Status);
        Assert.Single(w.Flow.Requests);
        Assert.Equal("Wrong cost center", outcome.Stages[0].Comments);
    }

    [Fact]
    public async Task No_answer_in_time_escalates_and_the_old_link_stops_working()
    {
        await using var w = await TestWorld.StartAsync();
        var id = await w.StartApprovalAsync(TestWorld.Invoice(), TestWorld.Settings(timeoutSeconds: 2));

        var first = await w.WaitForRequestAsync(1);
        var escalated = await w.WaitForRequestAsync(2);          // the durable timer fired
        Assert.Equal((People.Riley, "Manager approval escalated to riley.demo@contoso.com"), (escalated.ApproverEmail, escalated.StatusText));
        Assert.NotEqual(first.CallbackUrl, escalated.CallbackUrl);

        // Sam finally answers the old approval in Teams: refused, the request was replaced.
        var late = await w.AnswerAsync(first, "Approve", People.Sam);
        Assert.Equal(409, late.StatusCode);

        Assert.Equal(202, (await w.AnswerAsync(escalated, "Approve", People.Riley)).StatusCode);
        var outcome = await w.WaitForOutcomeAsync(id);
        Assert.Equal((ApprovalStatus.Approved, 2), (outcome.Status, outcome.Stages[0].Attempts));
        Assert.EndsWith("(escalated)", outcome.Summary);
    }

    [Fact]
    public async Task Nobody_answers_at_all_and_the_invoice_expires()
    {
        await using var w = await TestWorld.StartAsync();
        var id = await w.StartApprovalAsync(TestWorld.Invoice(), TestWorld.Settings(timeoutSeconds: 1));

        var outcome = await w.WaitForOutcomeAsync(id);
        Assert.Equal(ApprovalStatus.Expired, outcome.Status);
        Assert.Equal(2, w.Flow.Requests.Count);
        Assert.Equal(ApprovalStatus.Expired, Assert.Single(w.Flow.Outcomes).Status);
    }

    [Fact]
    public async Task Only_the_assigned_approver_can_answer()
    {
        await using var w = await TestWorld.StartAsync();
        var id = await w.StartApprovalAsync(TestWorld.Invoice(), TestWorld.Settings());
        var request = await w.WaitForRequestAsync(1);

        Assert.Equal(403, (await w.AnswerAsync(request, "Approve", People.Alex)).StatusCode);
        Assert.Equal(202, (await w.AnswerAsync(request, "Approve", "SAM.DEMO@contoso.com")).StatusCode);   // case-insensitive
        Assert.Equal(ApprovalStatus.Approved, (await w.WaitForOutcomeAsync(id)).Status);
    }

    [Fact]
    public async Task A_tampered_or_unsigned_callback_is_401()
    {
        await using var w = await TestWorld.StartAsync();
        await w.StartApprovalAsync(TestWorld.Invoice(), TestWorld.Settings());
        var (instanceId, requestId, sig) = TestWorld.ParseCallback((await w.WaitForRequestAsync(1)).CallbackUrl!);
        var body = new DecisionBody("Approve", People.Sam, null);

        Assert.Equal(401, (await DecisionHandler.HandleAsync(w.Client, w.Signer, instanceId, requestId, null, body)).StatusCode);
        Assert.Equal(401, (await DecisionHandler.HandleAsync(w.Client, w.Signer, "invoice-other-INV9", requestId, sig, body)).StatusCode);
        var otherKey = new CallbackSigner(Enumerable.Repeat((byte)7, 32).ToArray());
        Assert.Equal(401, (await DecisionHandler.HandleAsync(w.Client, otherKey, instanceId, requestId, sig, body)).StatusCode);
    }

    [Fact]
    public async Task Answers_after_completion_or_for_unknown_instances_are_refused()
    {
        await using var w = await TestWorld.StartAsync();
        var id = await w.StartApprovalAsync(TestWorld.Invoice(), TestWorld.Settings());
        var request = await w.WaitForRequestAsync(1);
        await w.AnswerAsync(request, "Reject", People.Sam);
        await w.WaitForOutcomeAsync(id);

        Assert.Equal(409, (await w.AnswerAsync(request, "Approve", People.Sam)).StatusCode);
        var ghost = "invoice-nobody-INV0";
        var reply = await DecisionHandler.HandleAsync(w.Client, w.Signer, ghost, "abc", w.Signer.Sign(ghost, "abc"),
            new DecisionBody("Approve", People.Sam, null));
        Assert.Equal(404, reply.StatusCode);
    }

    [Theory]
    [InlineData("approve")]
    [InlineData("Maybe")]
    [InlineData(null)]
    public async Task Outcome_must_be_Approve_or_Reject(string? outcome)
    {
        await using var w = await TestWorld.StartAsync();
        await w.StartApprovalAsync(TestWorld.Invoice(), TestWorld.Settings());
        var request = await w.WaitForRequestAsync(1);
        Assert.Equal(400, (await w.AnswerAsync(request, outcome!, People.Sam)).StatusCode);
    }

    [Fact]
    public async Task The_same_invoice_twice_starts_one_approval()
    {
        await using var w = await TestWorld.StartAsync();
        var invoice = TestWorld.Invoice();
        var first = await InvoiceIntake.StartAsync(w.Client, invoice, TestWorld.Settings());
        var second = await InvoiceIntake.StartAsync(w.Client, invoice, TestWorld.Settings());
        Assert.Equal((IntakeResult.Started, IntakeResult.AlreadyRunning), (first.Result, second.Result));
        Assert.Equal(first.InstanceId, second.InstanceId);

        await w.AnswerAsync(await w.WaitForRequestAsync(1), "Approve", People.Sam);
        await w.WaitForOutcomeAsync(first.InstanceId);
        var third = await InvoiceIntake.StartAsync(w.Client, invoice, TestWorld.Settings());
        Assert.Equal(IntakeResult.AlreadyFinished, third.Result);
        Assert.Single(w.Flow.Requests);
    }

    [Fact]
    public async Task An_expired_approval_can_be_started_again_a_rejected_one_cannot()
    {
        await using var w = await TestWorld.StartAsync();
        var invoice = TestWorld.Invoice();
        var id = await w.StartApprovalAsync(invoice, TestWorld.Settings(timeoutSeconds: 1));
        Assert.Equal(ApprovalStatus.Expired, (await w.WaitForOutcomeAsync(id)).Status);

        var again = await InvoiceIntake.StartAsync(w.Client, invoice, TestWorld.Settings());
        Assert.Equal(IntakeResult.Restarted, again.Result);
        await w.AnswerAsync(await w.WaitForRequestAsync(3), "Reject", People.Sam);
        Assert.Equal(ApprovalStatus.Rejected, (await w.WaitForOutcomeAsync(id)).Status);

        Assert.Equal(IntakeResult.AlreadyFinished, (await InvoiceIntake.StartAsync(w.Client, invoice, TestWorld.Settings())).Result);
    }

    [Fact]
    public async Task Custom_status_shows_who_has_the_invoice()
    {
        await using var w = await TestWorld.StartAsync();
        var id = await w.StartApprovalAsync(TestWorld.Invoice(), TestWorld.Settings());
        await w.WaitForRequestAsync(1);

        var meta = await w.Client.GetInstanceAsync(id, getInputsAndOutputs: true);
        var pending = meta!.ReadCustomStatusAs<PendingApproval>()!;
        Assert.Equal(("Manager", People.Sam, 1), (pending.Stage, pending.Approver, pending.Attempt));
    }
}
