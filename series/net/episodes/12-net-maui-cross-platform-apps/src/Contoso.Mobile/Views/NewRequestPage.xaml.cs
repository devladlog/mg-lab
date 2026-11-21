using Contoso.Mobile.Core.ViewModels;

namespace Contoso.Mobile.Views;

public partial class NewRequestPage : ContentPage
{
	public NewRequestPage(NewRequestViewModel viewModel)
	{
		InitializeComponent();
		BindingContext = viewModel;
		// The draft is stored (and sent if there is a network): close the form. The list page shows the result when it appears.
		viewModel.Submitted += async (_, _) =>
		{
			if (Shell.Current is { } shell) await shell.GoToAsync("..");
		};
	}
}
