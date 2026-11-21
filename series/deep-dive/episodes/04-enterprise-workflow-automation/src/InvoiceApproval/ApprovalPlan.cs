namespace Contoso.InvoiceApproval;

/// <summary>Who approves what. Pure function of the invoice and the settings captured at start.</summary>
public static class ApprovalPlan
{
    public static IReadOnlyList<Stage> For(InvoiceReady invoice, ApprovalSettings s)
    {
        var stages = new List<Stage> { Pick("Manager", s.ManagerEmail, s.EscalationEmail, invoice) };
        if (invoice.Total > s.FinanceThreshold)
            stages.Add(Pick("Finance", s.FinanceEmail, s.EscalationEmail, invoice));
        return stages;
    }

    /// <summary>Nobody approves an invoice they submitted: that stage goes straight to the escalation approver.</summary>
    static Stage Pick(string name, string approver, string escalation, InvoiceReady invoice)
    {
        if (string.Equals(approver, invoice.SubmittedBy, StringComparison.OrdinalIgnoreCase))
            return new Stage(name, escalation, EscalateTo: null);
        var escalateTo = string.Equals(escalation, approver, StringComparison.OrdinalIgnoreCase) ? null : escalation;
        return new Stage(name, approver, escalateTo);
    }
}
