using System.ComponentModel.DataAnnotations;
using System.Globalization;
using Contoso.Mobile.Core.Models;
using Contoso.Mobile.Core.Offline;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Contoso.Mobile.Core.ViewModels;

public partial class NewRequestViewModel(IOutbox outbox, SyncService sync, TimeProvider clock) : ObservableObject
{
    public IReadOnlyList<string> Departments { get; } = ["FIN", "IT", "OPS"];

    /// <summary>How the user types numbers. A phone in Portugal types 12000,50. Defaults to the device culture.</summary>
    public IFormatProvider Culture { get; set; } = CultureInfo.CurrentCulture;

    [ObservableProperty] private string _title = "";
    [ObservableProperty] private string? _departmentCode;
    [ObservableProperty] private string _amountText = "";
    [ObservableProperty] private string _requestedBy = "";
    [ObservableProperty] private string _errors = "";
    [ObservableProperty] private string _result = "";
    [ObservableProperty] private bool _isBusy;

    /// <summary>Raised when the draft is safely stored. The page closes itself.</summary>
    public event EventHandler<string>? Submitted;

    [RelayCommand]
    private async Task SubmitAsync()
    {
        Result = "";
        if (!TryValidate(out var amount)) return;

        IsBusy = true;
        try
        {
            // Outbox first, send second: whatever happens next (no network, app killed), the user's request is on the device.
            var draft = new DraftRequest(Guid.NewGuid(), Title.Trim(), DepartmentCode!, amount, RequestedBy.Trim(), clock.GetUtcNow().UtcDateTime);
            await outbox.AddAsync(draft);

            var report = await sync.FlushAsync();
            var left = (await outbox.ListAsync()).FirstOrDefault(d => d.Key == draft.Key);
            Result = left switch
            {
                null => "Sent.",
                { NeedsAttention: true } => $"The server refused it: {left.Error}",
                _ => report.Skipped ? "Saved on this device. It will be sent when you are back online."
                                    : "Saved on this device. The server is not reachable right now; it will be sent later.",
            };
            if (left is not { NeedsAttention: true }) Submitted?.Invoke(this, Result);
        }
        finally { IsBusy = false; }
    }

    /// <summary>The same rules the server applies (episode 11), so the user hears about mistakes before the network does.</summary>
    private bool TryValidate(out decimal amount)
    {
        var problems = new List<string>();
        if (Title.Trim().Length is < 3 or > 100) problems.Add("Title: 3 to 100 characters.");
        if (DepartmentCode is null || !Departments.Contains(DepartmentCode)) problems.Add("Department: pick one.");
        if (!decimal.TryParse(AmountText, NumberStyles.Number, Culture, out amount) || amount is < 1 or > 10_000_000)
        {
            problems.Add("Amount: a number from 1 to 10,000,000.");
            amount = 0;
        }
        if (!new EmailAddressAttribute().IsValid(RequestedBy.Trim())) problems.Add("Requested by: a valid e-mail address.");

        Errors = string.Join(Environment.NewLine, problems);
        return problems.Count == 0;
    }
}
