using System.Globalization;

namespace ContosoPurchasing;

/// <summary>"Contoso Purchasing" (legacy): a plain Windows Forms window with no API. Control names and accessible
/// names are set so a desktop flow can find them with UI automation; the tab order is Supplier, Description, Amount, Save.</summary>
public sealed class MainForm : Form
{
    private readonly TextBox _supplier = new() { Name = "txtSupplier", AccessibleName = "Supplier", TabIndex = 0 };
    private readonly TextBox _description = new() { Name = "txtDescription", AccessibleName = "Description", TabIndex = 1 };
    private readonly TextBox _amount = new() { Name = "txtAmount", AccessibleName = "Amount", TabIndex = 2 };
    private readonly Button _save = new() { Name = "btnSave", AccessibleName = "Save order", Text = "Save order", TabIndex = 3 };
    private readonly Label _status = new() { Name = "lblStatus", AccessibleName = "Status", Text = "Ready", AutoSize = true };
    private readonly OrderLedger _ledger = new(OrderLedger.DefaultPath());

    public MainForm()
    {
        Text = "Contoso Purchasing";
        Width = 460; Height = 280;
        FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        var grid = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, Padding = new Padding(12) };
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        foreach (var (label, box) in new[] { ("Supplier", (Control)_supplier), ("Description", _description), ("Amount (EUR)", _amount) })
        {
            grid.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left });
            box.Dock = DockStyle.Fill;
            grid.Controls.Add(box);
        }
        grid.Controls.Add(new Label());
        grid.Controls.Add(_save);
        grid.Controls.Add(new Label());
        grid.Controls.Add(_status);
        Controls.Add(grid);
        AcceptButton = _save;
        _save.Click += (_, _) => Save();
    }

    private void Save()
    {
        var result = OrderValidator.Validate(_supplier.Text, _description.Text, _amount.Text, CultureInfo.CurrentCulture);
        if (!result.IsValid)
        {
            _status.Text = "Error: " + string.Join("; ", result.Errors);
            MessageBox.Show(this, string.Join(Environment.NewLine, result.Errors), "Contoso Purchasing", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        var order = _ledger.Append(_supplier.Text, _description.Text, result.Amount, Environment.UserName, DateTimeOffset.UtcNow);
        _status.Text = $"Saved {order.OrderNo}";
        MessageBox.Show(this, $"Order {order.OrderNo} saved.", "Contoso Purchasing", MessageBoxButtons.OK, MessageBoxIcon.Information);
        _supplier.Clear(); _description.Clear(); _amount.Clear(); _supplier.Focus();
    }
}
